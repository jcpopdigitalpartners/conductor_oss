from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import settings
from ..schemas import VideoRenderSpec


def parse_resolution(resolution: str) -> tuple[int, int]:
    width_text, height_text = resolution.lower().split("x", maxsplit=1)
    return int(width_text), int(height_text)


def _replace_tokens(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_tokens(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_tokens(item, replacements) for item in value]
    if isinstance(value, str):
        if value in replacements:
            return replacements[value]
        updated = value
        for token, replacement in replacements.items():
            if isinstance(replacement, (str, int, float)):
                updated = updated.replace(token, str(replacement))
        return updated
    return value


def build_comfyui_workflow(spec: VideoRenderSpec) -> dict[str, Any] | None:
    template_path = settings.comfyui_workflow_template_path
    if not template_path:
        return None

    path = Path(template_path)
    if not path.exists():
        return None

    width, height = parse_resolution(spec.resolution)
    replacements: dict[str, Any] = {
        "${prompt}": spec.prompt,
        "${negative_prompt}": spec.negative_prompt,
        "${seed}": spec.seed,
        "${width}": width,
        "${height}": height,
        "${fps}": spec.fps,
        "${duration_seconds}": spec.duration_seconds,
        "${frame_count}": spec.duration_seconds * spec.fps,
        "${output_filename}": f"{spec.job_id}-final.mp4",
        "${model_family}": spec.model_family,
        "${scene_prompts_json}": json.dumps(spec.scene_prompts),
    }
    for index, scene_prompt in enumerate(spec.scene_prompts, start=1):
        replacements[f"${{scene_prompt_{index}}}"] = scene_prompt

    template = json.loads(path.read_text(encoding="utf-8"))
    return _replace_tokens(template, replacements)
