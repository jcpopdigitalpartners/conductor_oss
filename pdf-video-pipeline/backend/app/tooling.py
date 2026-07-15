from __future__ import annotations

from pydantic import Field

from .schemas import StrictModel


class ToolSelection(StrictModel):
    name: str
    role: str
    license: str
    hosting_mode: str
    why_selected: str
    backup_option: str | None = None


class MVPProfile(StrictModel):
    supported_document_classes: list[str] = Field(default_factory=list)
    output_formats: list[str] = Field(default_factory=list)
    reviewer_roles: list[str] = Field(default_factory=list)
    primary_video_backend: str
    excluded_scope: list[str] = Field(default_factory=list)


class ToolingProfile(StrictModel):
    orchestration: ToolSelection
    ingress_api: ToolSelection
    object_storage: ToolSelection
    metadata_store: ToolSelection
    event_bus: ToolSelection
    pdf_parser: ToolSelection
    fallback_parser: ToolSelection
    inference_runtime: ToolSelection
    prompt_safety: ToolSelection
    response_safety: ToolSelection
    review_surface: ToolSelection
    keyframe_generation: ToolSelection
    video_generation: ToolSelection
    post_processing: ToolSelection
    mvp: MVPProfile


REFERENCE_TOOLING = ToolingProfile(
    orchestration=ToolSelection(
        name="Conductor OSS",
        role="Durable orchestration for parent and sub-workflows.",
        license="Apache-2.0",
        hosting_mode="self-hosted",
        why_selected="Supports HUMAN, HTTP, EVENT, SWITCH, DO_WHILE, and SUB_WORKFLOW tasks without vendor lock-in.",
    ),
    ingress_api=ToolSelection(
        name="FastAPI",
        role="Upload, schema, review, and render orchestration facade.",
        license="MIT",
        hosting_mode="self-hosted",
        why_selected="Small surface area, native JSON modeling, and a clean fit for Conductor HTTP tasks.",
    ),
    object_storage=ToolSelection(
        name="MinIO",
        role="Stores PDFs, extracted assets, manifests, and rendered outputs.",
        license="AGPL-3.0",
        hosting_mode="self-hosted",
        why_selected="S3-compatible storage keeps worker integrations simple across ingestion, review, and rendering.",
    ),
    metadata_store=ToolSelection(
        name="PostgreSQL",
        role="Stores job state, review state, lineage, and audit metadata.",
        license="PostgreSQL",
        hosting_mode="self-hosted",
        why_selected="Reliable relational state for workflow-adjacent data that should outlive individual worker runs.",
    ),
    event_bus=ToolSelection(
        name="RabbitMQ",
        role="Carries review-created and render-started events to external consumers.",
        license="MPL-2.0",
        hosting_mode="self-hosted",
        why_selected="Straightforward local deployment and a good fit for moderate-volume adapter events.",
        backup_option="Kafka",
    ),
    pdf_parser=ToolSelection(
        name="Docling",
        role="Primary PDF to structured JSON and markdown parser.",
        license="MIT",
        hosting_mode="self-hosted",
        why_selected="Strong layout understanding, OCR support, and local execution for sensitive document handling.",
    ),
    fallback_parser=ToolSelection(
        name="HURIDOCS PDF Layout Analysis",
        role="Fallback OCR and layout extraction for scanned or low-confidence pages.",
        license="AGPL-3.0",
        hosting_mode="self-hosted",
        why_selected="Adds page segmentation, reading order, and OCR on problematic scans without introducing proprietary services.",
    ),
    inference_runtime=ToolSelection(
        name="vLLM",
        role="Structured intent and tone inference in production.",
        license="Apache-2.0",
        hosting_mode="self-hosted GPU",
        why_selected="Higher-throughput structured outputs make it the better long-running worker target than a development-only runtime.",
        backup_option="Ollama for local prototyping",
    ),
    prompt_safety=ToolSelection(
        name="Llama Prompt Guard 2",
        role="Prompt injection and jailbreak screening on document-derived prompts.",
        license="Open weights",
        hosting_mode="self-hosted",
        why_selected="Fast first-pass prompt screening before expensive video or LLM work is queued.",
    ),
    response_safety=ToolSelection(
        name="Llama Guard 3",
        role="Safety classification for generation prompts and output summaries.",
        license="Open weights",
        hosting_mode="self-hosted",
        why_selected="Adds a second classifier layer around risky creative directions or generated summaries.",
    ),
    review_surface=ToolSelection(
        name="FastAPI + React reference review app",
        role="Human-in-the-loop approval surface for creative briefs and look-and-feel edits.",
        license="MIT",
        hosting_mode="self-hosted",
        why_selected="Keeps the adapter intentionally simple while leaving room to swap in a fuller OSS media review tool later.",
        backup_option="FreeFrame or ThinkClip",
    ),
    keyframe_generation=ToolSelection(
        name="ComfyUI (image workflow)",
        role="Storyboard and keyframe generation from approved creative briefs.",
        license="GPL-3.0",
        hosting_mode="self-hosted GPU",
        why_selected="Flexible node graphs make style presets and per-scene prompt shaping easier to operationalize.",
    ),
    video_generation=ToolSelection(
        name="ComfyUI + Wan 2.2",
        role="Primary GPU video generation path.",
        license="Apache-2.0 and open-source tooling",
        hosting_mode="self-hosted GPU",
        why_selected="Stronger stylization and controllability for a reference MVP built around approved creative direction.",
        backup_option="CogVideoX",
    ),
    post_processing=ToolSelection(
        name="FFmpeg",
        role="Muxing, subtitle burn-in, rendition output, and preview generation.",
        license="LGPL-2.1-or-later/GPL depending on build",
        hosting_mode="self-hosted",
        why_selected="Standard post-processing toolchain with broad format support and no hosted dependency.",
    ),
    mvp=MVPProfile(
        supported_document_classes=["marketing collateral", "product overview"],
        output_formats=["30s landscape explainer", "60s landscape marketing video"],
        reviewer_roles=["creative approver"],
        primary_video_backend="ComfyUI + Wan 2.2",
        excluded_scope=[
            "frame-accurate editorial review",
            "automatic voice clone generation",
            "multi-language localization",
            "multiple simultaneous render backends",
        ],
    ),
)
