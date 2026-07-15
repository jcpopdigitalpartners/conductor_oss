# PDF Video Pipeline

Reference implementation of a self-hosted Conductor OSS pipeline that:

- ingests PDF documents,
- extracts structured meaning,
- infers intent and tone,
- routes a human through look-and-feel approval,
- and generates a video-ready render spec using only open-source components.

## Project Layout

- `backend/`: FastAPI service that exposes stable JSON contracts, review endpoints, and render-spec helpers.
- `conductor/workflows/`: parent and sub-workflow JSON definitions for Conductor OSS.
- `review-ui/`: React review surface for human approval and brief edits.

## Reference Stack

- Orchestration: `Conductor OSS`
- API facade: `FastAPI`
- Object storage: `MinIO`
- Metadata: `PostgreSQL`
- Events: `RabbitMQ`
- Primary PDF parsing: `Docling`
- Fallback OCR/layout: `HURIDOCS PDF Layout Analysis`
- Intent/tone inference: `vLLM` in production, `Ollama` for local prototyping
- Safety: `Llama Prompt Guard 2` and `Llama Guard 3`
- Image/video workflows: `ComfyUI` with `Wan 2.2`
- Video fallback: `CogVideoX`
- Post-processing: `FFmpeg`

## Locked MVP Scope

- Supported documents: marketing collateral and product overview PDFs
- Output formats: 30-second and 60-second landscape videos
- Reviewer role: one creative approver
- Primary generation path: `ComfyUI + Wan 2.2`
- Explicitly out of scope: frame-accurate editorial review, localization, voice cloning, multiple concurrent video backends

## Backend Quick Start

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload
```

Key endpoints:

- `POST /ingest`
- `POST /document/parse`
- `POST /document/infer`
- `GET /document/understanding/{job_id}`
- `POST /creative-brief`
- `POST /reviews`
- `POST /reviews/{review_id}/decision`
- `POST /render/spec`
- `POST /render/jobs`
- `POST /assets/package`
- `GET /schemas`
- `GET /tooling/profile`
- `GET /mvp`

## Review UI Quick Start

```bash
cd review-ui
npm install
npm run dev
```

The UI expects the backend at `http://localhost:8000` by default.

## Conductor Workflows

Load the workflow definitions from `conductor/workflows/` in this order:

1. `document_understanding.json`
2. `hitl_style_review.json`
3. `video_rendering.json`
4. `pdf_to_video_pipeline.json`

The parent workflow uses sub-workflows for parsing/inference, human review, and video rendering to keep each stage independently replaceable.

To re-register all workflows after editing their JSON definitions:

```bash
cd /mnt/c/Users/jobec/projects/conductor_oss/pdf-video-pipeline
bash register_workflows.sh
```

Override the server if needed:

```bash
CONDUCTOR_SERVER_URL=http://localhost:8080/api bash register_workflows.sh
```
