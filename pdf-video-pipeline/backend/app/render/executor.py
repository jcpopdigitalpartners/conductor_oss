from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any
from uuid import UUID

from ..config import settings
from ..repository import get_render, save_render
from ..schemas import RenderJob, RenderStatus, utc_now
from ..storage import store_bytes
from .comfyui_client import ComfyUIClient
from .workflow_builder import build_comfyui_workflow, parse_resolution

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


_render_queue: Queue[str] = Queue()
_worker_started = False
_worker_lock = threading.Lock()


def enqueue_render_job(render_id: UUID) -> None:
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            worker = threading.Thread(target=_worker_loop, name="render-worker", daemon=True)
            worker.start()
            _worker_started = True
    _render_queue.put(str(render_id))


def _worker_loop() -> None:
    while True:
        render_id = _render_queue.get()
        try:
            try:
                _execute_render(UUID(render_id))
            except Exception:
                # Keep the worker alive even if one render crashes unexpectedly.
                pass
        finally:
            _render_queue.task_done()


def _persist(render: RenderJob, **updates: Any) -> RenderJob:
    updated = render.model_copy(update={"updated_at": utc_now(), **updates})
    return save_render(updated)


def _execute_render(render_id: UUID) -> None:
    render = get_render(render_id)
    if render is None:
        return

    render = _persist(
        render,
        status=RenderStatus.RUNNING,
        progress=0.15,
        started_at=render.started_at or utc_now(),
        error_message=None,
    )

    try:
        final_bytes, preview_bytes, external_job_id, render_backend, used_fallback = _render_video(render)
        store_bytes(render.spec.output_location, final_bytes, content_type="video/mp4")
        if render.preview_location is not None and preview_bytes is not None:
            store_bytes(render.preview_location, preview_bytes, content_type="video/mp4")

        _persist(
            render,
            status=RenderStatus.COMPLETED,
            progress=1.0,
            external_job_id=external_job_id,
            render_backend=render_backend,
            used_fallback=used_fallback,
            final_video_location=render.spec.output_location,
            completed_at=utc_now(),
        )
    except Exception as exc:
        _persist(
            render,
            status=RenderStatus.FAILED,
            progress=1.0,
            error_message=str(exc),
            completed_at=utc_now(),
        )


def _render_video(render: RenderJob) -> tuple[bytes, bytes | None, str | None, str, bool]:
    workflow = build_comfyui_workflow(render.spec)
    if settings.comfyui_base_url and workflow is not None:
        try:
            return _render_with_comfyui(render, workflow)
        except Exception:
            if not settings.render_dev_fallback_enabled:
                raise

    if settings.render_dev_fallback_enabled:
        return _render_synthetic_mp4(render), None, None, "synthetic-fallback", True

    raise RuntimeError("No ComfyUI workflow is configured and render fallback is disabled")


def _render_with_comfyui(
    render: RenderJob, workflow: dict[str, Any]
) -> tuple[bytes, bytes | None, str | None, str, bool]:
    client = ComfyUIClient(settings.comfyui_base_url)
    prompt_id = client.submit_prompt(workflow)

    persisted = get_render(render.render_id)
    if persisted is not None:
        _persist(persisted, external_job_id=prompt_id, progress=0.3)

    deadline = time.time() + settings.render_timeout_seconds
    while time.time() < deadline:
        history = client.get_history(prompt_id)
        outputs = _extract_comfyui_outputs(history, prompt_id)
        if outputs is not None:
            return outputs[0], outputs[1], prompt_id, "comfyui-wan", False
        time.sleep(settings.render_poll_interval_seconds)

    raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")


def _extract_comfyui_outputs(
    history: dict[str, Any], prompt_id: str
) -> tuple[bytes, bytes | None] | None:
    prompt_history = history.get(prompt_id, history)
    outputs = prompt_history.get("outputs") or {}
    video_assets: list[dict[str, Any]] = []
    image_assets: list[dict[str, Any]] = []

    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        video_assets.extend(node_output.get("videos") or [])
        image_assets.extend(node_output.get("images") or [])

    client = ComfyUIClient(settings.comfyui_base_url)
    if video_assets:
        asset = video_assets[0]
        return (
            client.fetch_output(
                filename=asset["filename"],
                subfolder=asset.get("subfolder", ""),
                folder_type=asset.get("type", "output"),
            ),
            None,
        )

    if image_assets:
        image_bytes = [
            client.fetch_output(
                filename=asset["filename"],
                subfolder=asset.get("subfolder", ""),
                folder_type=asset.get("type", "output"),
            )
            for asset in image_assets
        ]
        return (_images_to_mp4(image_bytes), None)

    return None


def _render_synthetic_mp4(render: RenderJob) -> bytes:
    if cv2 is None or np is None:
        raise RuntimeError("Synthetic render fallback requires cv2 and numpy")

    width, height = parse_resolution(render.spec.resolution)
    fps = max(1, render.spec.fps)
    duration_seconds = max(2, min(render.spec.duration_seconds, 6))
    total_frames = fps * duration_seconds

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        writer = cv2.VideoWriter(
            str(temp_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not open an MP4 writer")

        scene_cards = render.spec.scene_prompts or [render.spec.prompt]
        palette = [
            (15, 23, 42),
            (29, 78, 216),
            (245, 158, 11),
        ]

        for frame_index in range(total_frames):
            scene_index = min(len(scene_cards) - 1, frame_index * len(scene_cards) // max(1, total_frames))
            color = palette[scene_index % len(palette)]
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:] = color

            _draw_text_block(
                frame,
                [
                    "PDF to Video Pipeline",
                    render.spec.model_family,
                    scene_cards[scene_index],
                ],
                origin_x=32,
                origin_y=60,
                line_height=34,
                max_width_chars=52,
            )
            cv2.putText(
                frame,
                f"frame {frame_index + 1}/{total_frames}",
                (40, height - 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            writer.write(frame)

        writer.release()
        return temp_path.read_bytes()
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _draw_text_block(
    frame: Any,
    lines: list[str],
    *,
    origin_x: int,
    origin_y: int,
    line_height: int,
    max_width_chars: int,
) -> None:
    y = origin_y
    for index, line in enumerate(lines):
        font_scale = 1.0 if index == 0 else 0.6
        thickness = 2 if index < 2 else 1
        color = (255, 255, 255) if index != 1 else (240, 240, 240)
        for wrapped in _wrap_text(line, max_width_chars):
            cv2.putText(
                frame,
                wrapped,
                (origin_x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                thickness,
                cv2.LINE_AA,
            )
            y += line_height
        y += 8


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _images_to_mp4(image_bytes: list[bytes]) -> bytes:
    if cv2 is None or np is None:
        raise RuntimeError("Converting ComfyUI images to MP4 requires cv2 and numpy")

    frames = []
    for payload in image_bytes:
        frame_array = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise RuntimeError("ComfyUI returned image outputs, but none could be decoded")

    height, width, _ = frames[0].shape
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        writer = cv2.VideoWriter(
            str(temp_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            12,
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not open an MP4 writer")
        for frame in frames:
            writer.write(frame)
        writer.release()
        return temp_path.read_bytes()
    finally:
        if temp_path.exists():
            temp_path.unlink()
