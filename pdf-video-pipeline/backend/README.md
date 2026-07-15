# Backend

FastAPI reference backend for the OSS PDF-to-video pipeline.

The backend now supports:

- storing uploaded PDF binaries in MinIO-compatible object storage
- persisting extracted markdown/text assets in the parsed bucket
- extracting PDF content through Docling when available, with a fallback parser for local development
- persisting async render jobs in SQLite so Conductor can poll durable state
- queueing render work through a ComfyUI-ready executor with a local MP4 fallback for development verification

## Run

```bash
pip install -e .
uvicorn app.main:app --reload
```

Optional storage/parser environment variables:

```bash
export MINIO_ENABLED=false
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_SECURE=false
export OBJECT_STORE_PATH=./data/object_store
```

Set `MINIO_ENABLED=true` only when you actually have a MinIO-compatible endpoint running. Otherwise the backend uses the local object-store directory immediately, which keeps local development and tests fast.

If MinIO or Docling is unavailable, the backend falls back to a local object-store directory plus a lightweight PDF extraction path so the reference app still runs in development.

Optional render environment variables:

```bash
export COMFYUI_BASE_URL=http://localhost:8188
export COMFYUI_WORKFLOW_TEMPLATE_PATH=/absolute/path/to/wan-workflow.json
export RENDER_POLL_INTERVAL_SECONDS=5
export RENDER_TIMEOUT_SECONDS=900
export RENDER_DEV_FALLBACK_ENABLED=true
```

When both `COMFYUI_BASE_URL` and `COMFYUI_WORKFLOW_TEMPLATE_PATH` are configured, the backend submits render prompts to ComfyUI and polls for completion. If they are not configured, the development fallback writes a real MP4 artifact locally so the full workflow can still be exercised end to end.

For real render validation, set:

```bash
export RENDER_DEV_FALLBACK_ENABLED=false
export EXPECT_REAL_RENDER=true
```

That combination makes the backend refuse synthetic fallback output and makes `e2e_render_check.py` fail if the workflow still falls back.

Document understanding artifacts inferred via `POST /document/infer` are now persisted by `job_id` and can be retrieved later with `GET /document/understanding/{job_id}`.

## Backend Helpers

From WSL, you can stop or restart the backend with:

```bash
cd /mnt/c/Users/jobec/projects/conductor_oss/pdf-video-pipeline/backend
bash stop_backend.sh
bash restart_backend.sh
```

`stop_backend.sh`:

- finds processes listening on port `8000`
- stops them cleanly

`restart_backend.sh`:

- activates `.venv`
- stops any process already listening on port `8000`
- starts `uvicorn app.main:app --reload`

## End-to-End Smoke Test

After the backend is running and the Conductor workflows are registered, you can verify upload -> approval -> render -> package with:

```bash
cd /mnt/c/Users/jobec/projects/conductor_oss/pdf-video-pipeline/backend
python e2e_render_check.py
```

The smoke test uploads a PDF, starts the parent workflow, waits for the `HUMAN` review gate, submits an approval, polls the workflow to completion, and prints the final MP4 and manifest paths from the local object store, including which render backend produced the artifact.
