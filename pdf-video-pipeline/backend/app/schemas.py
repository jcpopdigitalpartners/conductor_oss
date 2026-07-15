from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentSourceType(str, Enum):
    DIGITAL = "digital"
    SCANNED = "scanned"
    MIXED = "mixed"


class DocumentType(str, Enum):
    MARKETING = "marketing_collateral"
    PRODUCT = "product_overview"
    CASE_STUDY = "case_study"
    WHITEPAPER = "whitepaper"
    PROPOSAL = "proposal"
    TRAINING = "training_material"
    UNKNOWN = "unknown"


class IntentLabel(str, Enum):
    EDUCATE = "educate"
    PERSUADE = "persuade"
    ANNOUNCE = "announce"
    RECRUIT = "recruit"
    SELL = "sell"
    SUMMARIZE = "summarize"


class ToneLabel(str, Enum):
    HEROIC = "heroic"
    PROFESSIONAL = "professional"
    OPTIMISTIC = "optimistic"
    EMPATHETIC = "empathetic"
    URGENT = "urgent"
    PLAYFUL = "playful"
    NEUTRAL = "neutral"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class WorkflowLaunchStatus(str, Enum):
    STAGED = "staged"
    STARTING = "starting"
    STARTED = "started"


class RenderStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StorageLocation(StrictModel):
    bucket: str = Field(..., examples=["raw"])
    key: str = Field(..., examples=["jobs/123/source.pdf"])
    uri: str = Field(..., examples=["s3://raw/jobs/123/source.pdf"])


class PageExtraction(StrictModel):
    page_number: int = Field(..., ge=1)
    confidence: float = Field(..., ge=0, le=1)
    contains_images: bool = False
    contains_tables: bool = False
    preview_text: str = ""
    extracted_visual_cues: list[str] = Field(default_factory=list)


class DocumentSection(StrictModel):
    heading: str
    summary: str
    page_numbers: list[int] = Field(default_factory=list)


class BrandHint(StrictModel):
    label: str
    value: str
    confidence: float = Field(..., ge=0, le=1)


class DocumentProfile(StrictModel):
    job_id: UUID
    filename: str
    source_type: DocumentSourceType
    document_type: DocumentType
    storage: StorageLocation
    extracted_text_location: StorageLocation | None = None
    detected_language: str = "en"
    page_count: int = Field(..., ge=1)
    scanned_page_ratio: float = Field(..., ge=0, le=1)
    extraction_confidence: float = Field(..., ge=0, le=1)
    summary: str
    sections: list[DocumentSection] = Field(default_factory=list)
    page_details: list[PageExtraction] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    visual_cues: list[str] = Field(default_factory=list)
    brand_hints: list[BrandHint] = Field(default_factory=list)
    parser_used: str = Field(..., examples=["docling"])
    fallback_used: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class IntentToneProfile(StrictModel):
    job_id: UUID
    audience: str
    intent: IntentLabel
    tone: ToneLabel
    key_messages: list[str] = Field(default_factory=list)
    call_to_action: str
    visual_keywords: list[str] = Field(default_factory=list)
    prohibited_themes: list[str] = Field(default_factory=list)
    risky_content: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)
    rationale: str
    created_at: datetime = Field(default_factory=utc_now)


class DocumentUnderstanding(StrictModel):
    job_id: UUID
    document: DocumentProfile
    intent_tone: IntentToneProfile
    created_at: datetime = Field(default_factory=utc_now)


class CreativeScene(StrictModel):
    scene_number: int = Field(..., ge=1)
    title: str
    narration: str
    visual_prompt: str
    motion_direction: str
    duration_seconds: int = Field(..., ge=1, le=30)


class CreativeBrief(StrictModel):
    job_id: UUID
    summary: str
    style_direction: str
    look_and_feel_prompt: str
    palette: list[str] = Field(default_factory=list)
    typography: list[str] = Field(default_factory=list)
    pacing: str
    camera_language: list[str] = Field(default_factory=list)
    soundtrack_direction: str
    aspect_ratio: str = Field(..., examples=["16:9"])
    target_duration_seconds: int = Field(..., ge=15, le=120)
    key_messages: list[str] = Field(default_factory=list)
    visual_references: list[str] = Field(default_factory=list)
    scenes: list[CreativeScene] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ReviewDecision(StrictModel):
    review_id: UUID
    job_id: UUID
    status: ReviewStatus
    reviewer_id: str
    reviewer_notes: str = ""
    edited_look_and_feel_prompt: str | None = None
    edited_palette: list[str] = Field(default_factory=list)
    structured_delta: dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=utc_now)


class VideoRenderSpec(StrictModel):
    job_id: UUID
    model_family: str = Field(..., examples=["wan-2.2"])
    workflow_name: str = Field(..., examples=["approved-hero-landscape-v1"])
    seed: int = Field(..., ge=0)
    duration_seconds: int = Field(..., ge=15, le=120)
    fps: int = Field(..., ge=12, le=60)
    aspect_ratio: str = Field(..., examples=["16:9"])
    resolution: str = Field(..., examples=["1920x1080"])
    prompt: str
    negative_prompt: str
    audio_enabled: bool = True
    subtitles_enabled: bool = True
    scene_prompts: list[str] = Field(default_factory=list)
    output_location: StorageLocation
    created_at: datetime = Field(default_factory=utc_now)


class IngestRequest(StrictModel):
    filename: str
    source_bucket: str = "raw"
    desired_output_bucket: str = "final"
    tags: list[str] = Field(default_factory=list)


class IngestResponse(StrictModel):
    job_id: UUID
    source: StorageLocation
    output_bucket: str


class ParseDocumentRequest(StrictModel):
    job_id: UUID
    filename: str
    source: StorageLocation
    page_count: int = Field(default=4, ge=1)
    hint_document_type: DocumentType | None = None
    extracted_text: str = ""
    extracted_text_location: StorageLocation | None = None
    scanned_page_ratio: float = Field(default=0.0, ge=0, le=1)
    parser_used: str | None = None
    fallback_used: bool | None = None


class InferDocumentUnderstandingRequest(StrictModel):
    document: DocumentProfile


class BuildCreativeBriefRequest(StrictModel):
    document_understanding: DocumentUnderstanding
    requested_look_and_feel: str | None = None


class CreateReviewRequest(StrictModel):
    creative_brief: CreativeBrief
    requested_by: str = "conductor"
    existing_review_id: UUID | None = None


class ReviewRecord(StrictModel):
    review_id: UUID
    creative_brief: CreativeBrief
    status: ReviewStatus
    requested_by: str
    packet_url: str | None = None
    workflow_name: str | None = None
    workflow_id: str | None = None
    workflow_status: WorkflowLaunchStatus = WorkflowLaunchStatus.STAGED
    workflow_started_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    latest_decision: ReviewDecision | None = None


class UpdateCreativeBriefRequest(StrictModel):
    creative_brief: CreativeBrief
    review_decision: ReviewDecision


class CreateRenderSpecRequest(StrictModel):
    creative_brief: CreativeBrief
    review_decision: ReviewDecision


class RenderJob(StrictModel):
    render_id: UUID
    spec: VideoRenderSpec
    status: RenderStatus
    progress: float = Field(default=0, ge=0, le=1)
    render_backend: str = "unknown"
    used_fallback: bool = False
    external_job_id: str | None = None
    preview_location: StorageLocation | None = None
    final_video_location: StorageLocation | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class CreateRenderJobRequest(StrictModel):
    spec: VideoRenderSpec


class PackageAssetsRequest(StrictModel):
    job_id: UUID
    render: RenderJob
    review_decision: ReviewDecision


class PackageAssetsResponse(StrictModel):
    job_id: UUID
    render_backend: str
    used_fallback: bool = False
    manifest_location: StorageLocation
    final_video_location: StorageLocation
    included_assets: list[str] = Field(default_factory=list)


DocumentParseResult = DocumentProfile
