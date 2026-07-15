from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from urllib import error, request

API_BASE = "http://localhost:8000"
CONDUCTOR_BASE = "http://localhost:8080/api"
OBJECT_STORE = Path("./data/object_store")
EXPECT_REAL_RENDER = os.getenv("EXPECT_REAL_RENDER", "false").lower() == "true"


def json_request(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        detail = body
        if body:
            try:
                payload_json = json.loads(body)
                detail = payload_json.get("detail", body)
            except json.JSONDecodeError:
                detail = body
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc
    return json.loads(body) if body else {}


def multipart_upload(url: str, filename: str, file_bytes: bytes, fields: dict[str, str]) -> dict:
    boundary = f"----CursorBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def make_pdf_bytes() -> bytes:
    lines = [
        "Healthcare automation platform",
        "Accelerate approvals with guided workflows",
        "Request a demo today",
    ]
    stream_lines = ["BT", "/F1 18 Tf", "72 720 Td"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_lines.extend([f"({escaped}) Tj", "0 -28 Td"])
    stream_lines.append("ET")
    content_stream = "\n".join(stream_lines)

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_stream.encode('utf-8'))} >>\nstream\n{content_stream}\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode("utf-8"))

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(pdf)


def storage_path(location: dict[str, str]) -> Path:
    return OBJECT_STORE / location["bucket"] / location["key"]


def main() -> None:
    review = multipart_upload(
        f"{API_BASE}/reviews/upload-pdf",
        "e2e_render.pdf",
        make_pdf_bytes(),
        {"requested_look_and_feel": "hero design", "requested_by": "e2e-script"},
    )
    print(f"uploaded review {review['review_id']}")

    started = json_request("POST", f"{API_BASE}/reviews/{review['review_id']}/start-workflow")
    workflow_id = started["workflow_id"]
    print(f"started workflow {workflow_id}")

    decision = {
        "review_id": review["review_id"],
        "job_id": review["creative_brief"]["job_id"],
        "status": "approved",
        "reviewer_id": "creative.approver",
        "reviewer_notes": "Approved in end-to-end verification.",
    }
    updated = {}
    for attempt in range(24):
        try:
            updated = json_request(
                "POST", f"{API_BASE}/reviews/{review['review_id']}/decision", decision
            )
            break
        except RuntimeError as exc:
            if "failed with 409" not in str(exc):
                raise
            print(f"approval retry {attempt + 1}: waiting for HUMAN task")
            time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for the Conductor HUMAN task to accept approval")
    print(f"submitted decision {updated['status']}")

    workflow = {}
    for attempt in range(60):
        workflow = json_request(
            "GET", f"{CONDUCTOR_BASE}/workflow/{workflow_id}?includeTasks=true"
        )
        status = workflow.get("status")
        print(f"poll {attempt + 1}: workflow={status}")
        if status in {"COMPLETED", "FAILED", "TERMINATED"}:
            break
        time.sleep(5)
    else:
        raise RuntimeError("Workflow did not reach a terminal state in time")

    if workflow.get("status") != "COMPLETED":
        render_output = workflow.get("output", {}).get("render_output") or {}
        render_job = render_output.get("render_job") or {}
        raise RuntimeError(
            json.dumps(
                {
                    "status": workflow.get("status"),
                    "render_backend": render_job.get("render_backend"),
                    "render_error": render_job.get("error_message"),
                    "render_status": render_job.get("status"),
                    "tasks": workflow.get("tasks", []),
                },
                indent=2,
            )
        )

    render_output = workflow["output"]["render_output"]
    render_job = render_output["render_job"]
    package = render_output["package"]
    if package is None:
        raise RuntimeError(
            json.dumps(
                {
                    "message": "Render workflow completed without packaged assets.",
                    "render_backend": render_job.get("render_backend"),
                    "render_error": render_job.get("error_message"),
                    "render_status": render_job.get("status"),
                    "quality_checks": render_output.get("quality_checks"),
                },
                indent=2,
            )
        )
    final_path = storage_path(package["final_video_location"])
    manifest_path = storage_path(package["manifest_location"])

    if not final_path.exists():
        raise RuntimeError(f"Final MP4 missing: {final_path}")
    if not manifest_path.exists():
        raise RuntimeError(f"Manifest missing: {manifest_path}")
    if EXPECT_REAL_RENDER and render_job.get("used_fallback"):
        raise RuntimeError(
            "Expected a real render backend, but the workflow used synthetic-fallback. "
            "Set COMFYUI_BASE_URL and COMFYUI_WORKFLOW_TEMPLATE_PATH, and disable fallback."
        )

    summary = {
        "workflow_id": workflow_id,
        "review_id": review["review_id"],
        "render_id": render_job["render_id"],
        "render_status": render_job["status"],
        "render_backend": render_job.get("render_backend"),
        "used_fallback": render_job.get("used_fallback"),
        "final_mp4": str(final_path.resolve()),
        "final_mp4_bytes": final_path.stat().st_size,
        "manifest": str(manifest_path.resolve()),
        "manifest_bytes": manifest_path.stat().st_size,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
