from __future__ import annotations

import json
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import settings
from .db import init_db
from .extractor import extract_pdf_content
from .render import enqueue_render_job
from .repository import (
    bootstrap_storage,
    get_document as get_document_record,
    get_document_understanding as get_document_understanding_record,
    get_render as get_render_record,
    get_review as get_review_record,
    get_review_packet as get_review_packet_html,
    list_reviews as list_review_records,
    persist_review_update,
    save_render,
    save_document,
    save_document_understanding,
    save_ingest,
)
from .schemas import (
    BuildCreativeBriefRequest,
    BrandHint,
    CreateRenderJobRequest,
    CreateRenderSpecRequest,
    CreateReviewRequest,
    CreativeBrief,
    CreativeScene,
    DocumentUnderstanding,
    DocumentProfile,
    DocumentSection,
    DocumentSourceType,
    DocumentType,
    IngestRequest,
    IngestResponse,
    InferDocumentUnderstandingRequest,
    IntentLabel,
    IntentToneProfile,
    PackageAssetsRequest,
    PackageAssetsResponse,
    PageExtraction,
    ParseDocumentRequest,
    RenderJob,
    RenderStatus,
    ReviewDecision,
    ReviewRecord,
    ReviewStatus,
    StorageLocation,
    ToneLabel,
    UpdateCreativeBriefRequest,
    VideoRenderSpec,
    WorkflowLaunchStatus,
    utc_now,
)
from .storage import load_bytes, store_bytes
from .tooling import REFERENCE_TOOLING

app = FastAPI(
    title="PDF Video Pipeline Backend",
    version="0.1.0",
    description="Reference backend for an OSS Conductor PDF-to-video workflow.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HITL_REVIEW_WORKFLOW_NAME = "hitl_style_review"


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def bucket_uri(bucket: str, key: str) -> StorageLocation:
    return StorageLocation(bucket=bucket, key=key, uri=f"s3://{bucket}/{key}")


def parsed_asset_uri(job_id: UUID, filename: str) -> StorageLocation:
    stem = filename.rsplit(".", 1)[0]
    key = f"jobs/{job_id}/parsed/{stem}.md"
    return bucket_uri(settings.minio_bucket_parsed, key)


def infer_document_type(text: str) -> DocumentType:
    lowered = text.lower()
    if any(token in lowered for token in ("case study", "customer story", "results")):
        return DocumentType.CASE_STUDY
    if any(token in lowered for token in ("whitepaper", "research", "analysis")):
        return DocumentType.WHITEPAPER
    if any(token in lowered for token in ("pricing", "offer", "buy now", "request a demo")):
        return DocumentType.MARKETING
    if any(token in lowered for token in ("product", "platform", "solution overview", "features")):
        return DocumentType.PRODUCT
    if any(token in lowered for token in ("training", "onboarding", "curriculum")):
        return DocumentType.TRAINING
    return DocumentType.UNKNOWN


def infer_source_type(scanned_page_ratio: float) -> DocumentSourceType:
    if scanned_page_ratio >= 0.8:
        return DocumentSourceType.SCANNED
    if scanned_page_ratio >= 0.25:
        return DocumentSourceType.MIXED
    return DocumentSourceType.DIGITAL


def build_sections(text: str) -> list[DocumentSection]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [
            DocumentSection(
                heading="Executive Summary",
                summary="No extracted text was supplied, so the parser created a placeholder summary.",
                page_numbers=[1],
            )
        ]

    sections: list[DocumentSection] = []
    chunk_size = 3
    for idx in range(0, min(len(lines), 9), chunk_size):
        chunk = lines[idx : idx + chunk_size]
        sections.append(
            DocumentSection(
                heading=chunk[0][:60],
                summary=" ".join(chunk)[:260],
                page_numbers=[(idx // chunk_size) + 1],
            )
        )
    return sections


def build_page_details(page_count: int, text: str, scanned_page_ratio: float) -> list[PageExtraction]:
    preview = text.replace("\n", " ").strip() or "No extracted text available."
    details: list[PageExtraction] = []
    for page in range(1, page_count + 1):
        confidence = 0.78 if scanned_page_ratio < 0.25 else 0.62
        details.append(
            PageExtraction(
                page_number=page,
                confidence=confidence,
                contains_images=page == 1,
                contains_tables="table" in preview.lower(),
                preview_text=preview[:200],
                extracted_visual_cues=["hero imagery", "clean typography"] if page == 1 else [],
            )
        )
    return details


def extract_entities(text: str) -> list[str]:
    candidates: list[str] = []
    for token in text.replace(",", " ").split():
        cleaned = token.strip().strip(".:;()")
        if len(cleaned) > 3 and cleaned[:1].isupper():
            candidates.append(cleaned)
    return sorted(dict.fromkeys(candidates))[:8]


def extract_visual_cues(text: str) -> list[str]:
    lowered = text.lower()
    cues = []
    if "hero" in lowered:
        cues.append("hero design")
    if "innovation" in lowered or "future" in lowered:
        cues.append("futuristic product lighting")
    if "customer" in lowered:
        cues.append("human-centered storytelling")
    if "security" in lowered:
        cues.append("high-trust interface motifs")
    return cues or ["cinematic motion graphics", "clean product spotlight"]


def build_document_profile(request: ParseDocumentRequest) -> DocumentProfile:
    summary = request.extracted_text.strip() or (
        f"{request.filename} was ingested for PDF-to-video conversion. "
        "The parser should replace this placeholder with extracted markdown or JSON."
    )
    document_type = request.hint_document_type or infer_document_type(summary)
    source_type = infer_source_type(request.scanned_page_ratio)
    parser_used = request.parser_used or ("docling" if request.scanned_page_ratio < 0.5 else "huridocs-fallback")
    extraction_confidence = 0.88 if source_type == DocumentSourceType.DIGITAL else 0.67
    fallback_used = request.fallback_used if request.fallback_used is not None else parser_used != "docling"

    return DocumentProfile(
        job_id=request.job_id,
        filename=request.filename,
        source_type=source_type,
        document_type=document_type,
        storage=request.source,
        extracted_text_location=request.extracted_text_location,
        page_count=request.page_count,
        scanned_page_ratio=request.scanned_page_ratio,
        extraction_confidence=extraction_confidence,
        summary=summary[:600],
        sections=build_sections(summary),
        page_details=build_page_details(request.page_count, summary, request.scanned_page_ratio),
        entities=extract_entities(summary),
        visual_cues=extract_visual_cues(summary),
        brand_hints=[
            BrandHint(label="style", value="hero design", confidence=0.74),
            BrandHint(label="palette", value="deep blue and warm amber", confidence=0.61),
        ],
        parser_used=parser_used,
        fallback_used=fallback_used,
    )


def infer_intent_tone(document: DocumentProfile) -> IntentToneProfile:
    lowered = document.summary.lower()
    if any(token in lowered for token in ("request a demo", "buy", "contact sales", "pricing")):
        intent = IntentLabel.SELL
        tone = ToneLabel.HEROIC
        audience = "buyers and decision makers"
    elif "case study" in lowered or "customer" in lowered:
        intent = IntentLabel.PERSUADE
        tone = ToneLabel.PROFESSIONAL
        audience = "prospective customers"
    elif "training" in lowered or "learn" in lowered:
        intent = IntentLabel.EDUCATE
        tone = ToneLabel.EMPATHETIC
        audience = "new users and internal teams"
    else:
        intent = IntentLabel.SUMMARIZE
        tone = ToneLabel.OPTIMISTIC
        audience = "general business stakeholders"

    return IntentToneProfile(
        job_id=document.job_id,
        audience=audience,
        intent=intent,
        tone=tone,
        key_messages=[section.summary[:100] for section in document.sections[:3]],
        call_to_action="Learn more about the solution and take the next review-approved action.",
        visual_keywords=document.visual_cues[:4],
        prohibited_themes=["graphic violence", "unsafe medical claims"],
        risky_content=["unverified claims"] if "guarantee" in lowered else [],
        confidence=0.82 if document.extraction_confidence > 0.75 else 0.68,
        rationale="Intent and tone were inferred from extracted claims, call-to-action language, and document style cues.",
    )


def infer_document_understanding(document: DocumentProfile) -> DocumentUnderstanding:
    intent_tone = infer_intent_tone(document)
    return DocumentUnderstanding(
        job_id=document.job_id,
        document=document,
        intent_tone=intent_tone,
    )


def build_creative_brief(request: BuildCreativeBriefRequest) -> CreativeBrief:
    document_understanding = request.document_understanding
    document = document_understanding.document
    intent_tone = document_understanding.intent_tone
    style_prompt = request.requested_look_and_feel or "hero design with premium motion graphics"
    opening_summary = document.sections[0].summary
    solution_summary = (
        intent_tone.key_messages[1] if len(intent_tone.key_messages) > 1 else intent_tone.key_messages[0]
    )
    visual_keywords = ", ".join(intent_tone.visual_keywords[:2]) or "clean product storytelling"
    scenes = [
        CreativeScene(
            scene_number=1,
            title="Opening problem statement",
            narration=opening_summary,
            visual_prompt=(
                f"{style_prompt}, opening reveal, cinematic intro, "
                f"document theme: {opening_summary}"
            ),
            motion_direction="Slow dolly-in with layered typography.",
            duration_seconds=15,
        ),
        CreativeScene(
            scene_number=2,
            title="Solution highlights",
            narration=solution_summary,
            visual_prompt=(
                f"{style_prompt}, product benefit, {visual_keywords}, "
                f"message focus: {solution_summary}"
            ),
            motion_direction="Parallax transitions over product-led imagery.",
            duration_seconds=15,
        ),
        CreativeScene(
            scene_number=3,
            title="Call to action",
            narration=intent_tone.call_to_action,
            visual_prompt=(
                f"{style_prompt}, confident closing frame, branded CTA card, "
                f"call to action: {intent_tone.call_to_action}"
            ),
            motion_direction="Push-in to logo lockup and CTA.",
            duration_seconds=15,
        ),
    ]
    return CreativeBrief(
        job_id=document.job_id,
        summary=f"{intent_tone.intent.value.replace('_', ' ').title()} video derived from {document.filename}.",
        style_direction=intent_tone.tone.value.replace("_", " "),
        look_and_feel_prompt=style_prompt,
        palette=["#0F172A", "#1D4ED8", "#F59E0B"],
        typography=["Inter", "Sora"],
        pacing="steady cinematic pacing with a strong finish",
        camera_language=["wide hero framing", "product push-in", "text-led transitions"],
        soundtrack_direction="uplifting, modern, confident",
        aspect_ratio=settings.default_aspect_ratio,
        target_duration_seconds=settings.default_duration_seconds,
        key_messages=intent_tone.key_messages,
        visual_references=document.visual_cues,
        scenes=scenes,
    )


def apply_review_delta(creative_brief: CreativeBrief, decision: ReviewDecision) -> CreativeBrief:
    patch = decision.structured_delta
    return creative_brief.model_copy(
        update={
            "look_and_feel_prompt": decision.edited_look_and_feel_prompt or creative_brief.look_and_feel_prompt,
            "palette": decision.edited_palette or creative_brief.palette,
            "pacing": patch.get("pacing", creative_brief.pacing),
            "camera_language": patch.get("camera_language", creative_brief.camera_language),
            "style_direction": patch.get("style_direction", creative_brief.style_direction),
        }
    )


def build_render_spec(request: CreateRenderSpecRequest) -> VideoRenderSpec:
    brief = request.creative_brief
    scene_prompts = [
        (
            f"Scene {scene.scene_number} - {scene.title}. "
            f"Narration: {scene.narration}. "
            f"Visual: {scene.visual_prompt}. "
            f"Motion: {scene.motion_direction}"
        )
        for scene in brief.scenes
    ]
    prompt = (
        f"Create a {brief.aspect_ratio} promotional video. "
        f"Look and feel: {brief.look_and_feel_prompt}. "
        f"Tone: {brief.style_direction}. "
        f"Palette: {', '.join(brief.palette)}. "
        f"Typography: {', '.join(brief.typography)}. "
        f"Key messages: {' | '.join(brief.key_messages)}. "
        f"Visual references: {' | '.join(brief.visual_references)}. "
        f"Scenes: {' || '.join(scene_prompts)}"
    )
    output_key = f"jobs/{brief.job_id}/renders/final.mp4"
    return VideoRenderSpec(
        job_id=brief.job_id,
        model_family=settings.primary_video_model,
        workflow_name="approved-hero-landscape-v1",
        seed=int(brief.job_id.int % 100000),
        duration_seconds=brief.target_duration_seconds,
        fps=settings.default_fps,
        aspect_ratio=brief.aspect_ratio,
        resolution=settings.default_resolution,
        prompt=prompt,
        negative_prompt="low resolution, distorted faces, broken hands, unreadable text, off-brand palette",
        audio_enabled=True,
        subtitles_enabled=True,
        scene_prompts=scene_prompts,
        output_location=bucket_uri(settings.minio_bucket_final, output_key),
    )


def build_review_from_uploaded_pdf(
    filename: str,
    pdf_bytes: bytes,
    requested_look_and_feel: str | None,
    requested_by: str,
) -> ReviewRecord:
    job_id = uuid4()
    source = bucket_uri(settings.minio_bucket_raw, f"jobs/{job_id}/source/{filename}")
    store_bytes(source, pdf_bytes, content_type="application/pdf")
    ingest = IngestResponse(
        job_id=job_id,
        source=source,
        output_bucket=settings.minio_bucket_final,
    )
    extracted_pdf = extract_pdf_content(filename, pdf_bytes)
    extracted_text_location = parsed_asset_uri(job_id, filename)
    store_bytes(
        extracted_text_location,
        extracted_pdf.markdown.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
    )
    document = build_document_profile(
        ParseDocumentRequest(
            job_id=job_id,
            filename=filename,
            source=source,
            page_count=extracted_pdf.page_count,
            hint_document_type=DocumentType.MARKETING,
            extracted_text=extracted_pdf.text,
            extracted_text_location=extracted_text_location,
            scanned_page_ratio=extracted_pdf.scanned_page_ratio,
            parser_used=extracted_pdf.parser_used,
            fallback_used=extracted_pdf.fallback_used,
        )
    )
    document_understanding = infer_document_understanding(document)
    creative_brief = build_creative_brief(
        BuildCreativeBriefRequest(
            document_understanding=document_understanding,
            requested_look_and_feel=requested_look_and_feel or "hero design",
        )
    )
    review = ReviewRecord(
        review_id=uuid4(),
        creative_brief=creative_brief,
        status=ReviewStatus.PENDING,
        requested_by=requested_by,
        workflow_name=settings.conductor_workflow_name,
    )
    return bootstrap_storage(
        ingest=ingest,
        document=document,
        document_understanding=document_understanding,
        review=review,
    )


def build_workflow_input(review: ReviewRecord) -> dict[str, Any]:
    document = get_document_record(review.creative_brief.job_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found for review")

    extracted_text = document.summary
    if document.extracted_text_location is not None:
        try:
            extracted_text = load_bytes(document.extracted_text_location).decode("utf-8").strip() or document.summary
        except FileNotFoundError:
            extracted_text = document.summary

    return {
        "existing_review_id": str(review.review_id),
        "filename": document.filename,
        "requested_look_and_feel": review.creative_brief.look_and_feel_prompt,
        "reviewer_id": "creative.approver",
        "page_count": document.page_count,
        "extracted_text": extracted_text,
        "scanned_page_ratio": document.scanned_page_ratio,
        "hint_document_type": document.document_type.value,
    }


def conductor_json_request(
    api_path: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
) -> Any:
    request_body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if request_body is not None:
        headers["Content-Type"] = "application/json"

    request = urllib_request.Request(
        f"{settings.conductor_base_url}{api_path}",
        data=request_body,
        headers=headers,
        method=method,
    )

    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8").strip()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise HTTPException(status_code=502, detail=f"Conductor request failed: {detail}") from exc
    except urllib_error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach Conductor: {exc.reason}") from exc

    if not response_body:
        return None

    try:
        return json.loads(response_body)
    except json.JSONDecodeError:
        return response_body


def find_human_task_in_workflow(
    workflow_id: str,
    review_id: UUID,
    visited_workflow_ids: set[str] | None = None,
) -> dict[str, str] | None:
    visited = visited_workflow_ids if visited_workflow_ids is not None else set()
    if workflow_id in visited:
        return None
    visited.add(workflow_id)

    workflow = conductor_json_request(f"/workflow/{workflow_id}?includeTasks=true")
    tasks = workflow.get("tasks") or []

    for task in tasks:
        input_data = task.get("inputData") or {}
        task_type = task.get("taskType") or task.get("type")
        if (
            task_type == "HUMAN"
            and task.get("status") == "IN_PROGRESS"
            and str(input_data.get("review_id")) == str(review_id)
        ):
            task_id = task.get("taskId")
            workflow_instance_id = task.get("workflowInstanceId") or workflow.get("workflowId") or workflow_id
            if task_id and workflow_instance_id:
                return {
                    "task_id": str(task_id),
                    "workflow_instance_id": str(workflow_instance_id),
                }

    for task in tasks:
        task_type = task.get("taskType") or task.get("type")
        if task_type != "SUB_WORKFLOW":
            continue

        output_data = task.get("outputData") or {}
        subworkflow_id = task.get("subWorkflowId") or output_data.get("subWorkflowId")
        if not subworkflow_id:
            continue

        found = find_human_task_in_workflow(str(subworkflow_id), review_id, visited)
        if found is not None:
            return found

    return None


def find_waiting_human_review_task(review: ReviewRecord) -> dict[str, str] | None:
    candidate_workflow_ids: list[str] = []
    if review.workflow_id:
        candidate_workflow_ids.append(review.workflow_id)

    running_hitl_workflow_ids = conductor_json_request(f"/workflow/running/{HITL_REVIEW_WORKFLOW_NAME}")
    if isinstance(running_hitl_workflow_ids, list):
        candidate_workflow_ids.extend(str(workflow_id) for workflow_id in running_hitl_workflow_ids)

    visited_workflow_ids: set[str] = set()
    for workflow_id in dict.fromkeys(candidate_workflow_ids):
        found = find_human_task_in_workflow(workflow_id, review.review_id, visited_workflow_ids)
        if found is not None:
            return found

    return None


def complete_waiting_human_review_task(review: ReviewRecord, decision: ReviewDecision) -> None:
    task_execution = find_waiting_human_review_task(review)
    if task_execution is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Review decision was saved, but no waiting Conductor HUMAN task was found for this review."
            ),
        )

    conductor_json_request(
        "/tasks",
        method="POST",
        payload={
            "workflowInstanceId": task_execution["workflow_instance_id"],
            "taskId": task_execution["task_id"],
            "status": "COMPLETED",
            "outputData": {
                "review_id": str(review.review_id),
                "job_id": str(review.creative_brief.job_id),
                "review_status": decision.status.value,
                "review_decision": decision.model_dump(mode="json"),
                "packet_url": review.packet_url,
            },
        },
    )


def start_conductor_workflow(review: ReviewRecord) -> ReviewRecord:
    if review.workflow_status == WorkflowLaunchStatus.STARTED and review.workflow_id:
        return review
    if review.workflow_status == WorkflowLaunchStatus.STARTING:
        return review

    starting_review = review.model_copy(
        update={
            "workflow_name": settings.conductor_workflow_name,
            "workflow_status": WorkflowLaunchStatus.STARTING,
            "workflow_started_at": utc_now() if review.workflow_started_at is None else review.workflow_started_at,
        }
    )
    persisted_starting_review = persist_review_update(starting_review)

    payload = {
        "name": settings.conductor_workflow_name,
        "version": settings.conductor_workflow_version,
        "correlationId": str(review.review_id),
        "input": build_workflow_input(review),
    }
    api_url = f"{settings.conductor_base_url}/workflow"
    request_body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        api_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/plain",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            workflow_id = response.read().decode("utf-8").strip().strip('"')
    except urllib_error.HTTPError as exc:
        persist_review_update(
            persisted_starting_review.model_copy(update={"workflow_status": WorkflowLaunchStatus.STAGED})
        )
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise HTTPException(status_code=502, detail=f"Conductor rejected workflow start: {detail}") from exc
    except urllib_error.URLError as exc:
        persist_review_update(
            persisted_starting_review.model_copy(update={"workflow_status": WorkflowLaunchStatus.STAGED})
        )
        raise HTTPException(status_code=502, detail=f"Unable to reach Conductor: {exc.reason}") from exc

    updated = persisted_starting_review.model_copy(
        update={
            "workflow_name": settings.conductor_workflow_name,
            "workflow_id": workflow_id,
            "workflow_status": WorkflowLaunchStatus.STARTED,
        }
    )
    return persist_review_update(updated)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/schemas")
def schemas() -> dict[str, Any]:
    return {
        "DocumentProfile": DocumentProfile.model_json_schema(),
        "DocumentUnderstanding": DocumentUnderstanding.model_json_schema(),
        "IntentToneProfile": IntentToneProfile.model_json_schema(),
        "CreativeBrief": CreativeBrief.model_json_schema(),
        "ReviewDecision": ReviewDecision.model_json_schema(),
        "VideoRenderSpec": VideoRenderSpec.model_json_schema(),
    }


@app.get("/tooling/profile")
def tooling_profile() -> dict[str, Any]:
    return REFERENCE_TOOLING.model_dump(mode="json")


@app.get("/mvp")
def mvp_profile() -> dict[str, Any]:
    return REFERENCE_TOOLING.mvp.model_dump(mode="json")


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    job_id = uuid4()
    key = f"jobs/{job_id}/source/{request.filename}"
    response = IngestResponse(
        job_id=job_id,
        source=bucket_uri(request.source_bucket, key),
        output_bucket=request.desired_output_bucket,
    )
    save_ingest(response)
    return response


@app.post("/document/parse", response_model=DocumentProfile)
def parse_document(request: ParseDocumentRequest) -> DocumentProfile:
    parse_request = request
    if not request.extracted_text.strip():
        try:
            payload = load_bytes(request.source)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Source document bytes not found in object storage") from exc

        extracted_pdf = extract_pdf_content(request.filename, payload)
        extracted_text_location = request.extracted_text_location or parsed_asset_uri(request.job_id, request.filename)
        store_bytes(
            extracted_text_location,
            extracted_pdf.markdown.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        parse_request = request.model_copy(
            update={
                "page_count": extracted_pdf.page_count,
                "extracted_text": extracted_pdf.text,
                "extracted_text_location": extracted_text_location,
                "scanned_page_ratio": extracted_pdf.scanned_page_ratio,
                "parser_used": extracted_pdf.parser_used,
                "fallback_used": extracted_pdf.fallback_used,
            }
        )

    profile = build_document_profile(parse_request)
    save_document(profile)
    return profile


@app.post("/document/infer", response_model=DocumentUnderstanding)
def infer_document_understanding_endpoint(
    request: InferDocumentUnderstandingRequest,
) -> DocumentUnderstanding:
    document_understanding = infer_document_understanding(request.document)
    save_document_understanding(document_understanding)
    return document_understanding


@app.get("/document/understanding/{job_id}", response_model=DocumentUnderstanding)
def get_document_understanding(job_id: UUID) -> DocumentUnderstanding:
    document_understanding = get_document_understanding_record(job_id)
    if document_understanding is None:
        raise HTTPException(status_code=404, detail="Document understanding not found")
    return document_understanding


@app.post("/creative-brief", response_model=CreativeBrief)
def create_creative_brief(request: BuildCreativeBriefRequest) -> CreativeBrief:
    return build_creative_brief(request)


@app.post("/creative-brief/revise", response_model=CreativeBrief)
def revise_creative_brief(request: UpdateCreativeBriefRequest) -> CreativeBrief:
    return apply_review_delta(request.creative_brief, request.review_decision)


@app.post("/reviews", response_model=ReviewRecord)
def create_review(request: CreateReviewRequest) -> ReviewRecord:
    existing_review = None
    if request.existing_review_id is not None:
        existing_review = get_review_record(request.existing_review_id)
        if existing_review is None:
            raise HTTPException(status_code=404, detail="Existing review not found")

    review = (
        existing_review.model_copy(
            update={
                "creative_brief": request.creative_brief,
                "status": ReviewStatus.PENDING,
                "latest_decision": None,
            }
        )
        if existing_review is not None
        else ReviewRecord(
            review_id=uuid4(),
            creative_brief=request.creative_brief,
            status=ReviewStatus.PENDING,
            requested_by=request.requested_by,
            workflow_name=settings.conductor_workflow_name,
        )
    )
    if get_document_record(review.creative_brief.job_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found for review")
    return persist_review_update(review)


@app.post("/reviews/upload-pdf", response_model=ReviewRecord)
async def upload_pdf_review(
    file: UploadFile = File(...),
    requested_look_and_feel: str | None = Form(default=None),
    requested_by: str = Form(default="review-ui"),
) -> ReviewRecord:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    payload = await file.read()
    return build_review_from_uploaded_pdf(
        filename=file.filename,
        pdf_bytes=payload,
        requested_look_and_feel=requested_look_and_feel,
        requested_by=requested_by,
    )


@app.get("/reviews", response_model=list[ReviewRecord])
def list_reviews(status: ReviewStatus | None = Query(default=None)) -> list[ReviewRecord]:
    return list_review_records(status)


@app.get("/reviews/{review_id}", response_model=ReviewRecord)
def get_review(review_id: UUID) -> ReviewRecord:
    review = get_review_record(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@app.get("/reviews/{review_id}/packet", response_class=HTMLResponse)
def get_review_packet(review_id: UUID) -> HTMLResponse:
    html_packet = get_review_packet_html(review_id)
    if html_packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    return HTMLResponse(content=html_packet)


@app.post("/reviews/{review_id}/decision", response_model=ReviewRecord)
def submit_review_decision(review_id: UUID, decision: ReviewDecision) -> ReviewRecord:
    review = get_review_record(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if decision.review_id != review_id:
        raise HTTPException(status_code=400, detail="Review identifier mismatch")
    updated = review.model_copy(update={"status": decision.status, "latest_decision": decision})
    persisted_review = persist_review_update(updated)

    if review.workflow_status == WorkflowLaunchStatus.STAGED and review.requested_by != "conductor":
        return persisted_review

    complete_waiting_human_review_task(persisted_review, decision)
    return persisted_review


@app.post("/reviews/{review_id}/start-workflow", response_model=ReviewRecord)
def start_review_workflow(review_id: UUID) -> ReviewRecord:
    review = get_review_record(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return start_conductor_workflow(review)


@app.post("/render/spec", response_model=VideoRenderSpec)
def create_render_spec(request: CreateRenderSpecRequest) -> VideoRenderSpec:
    if request.review_decision.status != ReviewStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Render specs require an approved review decision")
    return build_render_spec(request)


@app.post("/render/jobs", response_model=RenderJob)
def create_render_job(request: CreateRenderJobRequest) -> RenderJob:
    render = save_render(
        RenderJob(
        render_id=uuid4(),
        spec=request.spec,
        status=RenderStatus.QUEUED,
        progress=0.05,
        preview_location=bucket_uri(settings.minio_bucket_renders, f"jobs/{request.spec.job_id}/preview/storyboard.mp4"),
        final_video_location=request.spec.output_location,
        )
    )
    enqueue_render_job(render.render_id)
    return render


@app.get("/render/jobs/{render_id}", response_model=RenderJob)
def get_render_job(render_id: UUID) -> RenderJob:
    render = get_render_record(render_id)
    if render is None:
        raise HTTPException(status_code=404, detail="Render job not found")
    return render


@app.post("/assets/package", response_model=PackageAssetsResponse)
def package_assets(request: PackageAssetsRequest) -> PackageAssetsResponse:
    if request.review_decision.status != ReviewStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Packaging requires an approved review decision")
    if request.render.status != RenderStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Render job is not complete yet")

    try:
        load_bytes(request.render.spec.output_location)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Final video artifact was not found in object storage") from exc

    manifest = bucket_uri(settings.minio_bucket_final, f"jobs/{request.job_id}/manifest.json")
    final_video = request.render.spec.output_location
    package = PackageAssetsResponse(
        job_id=request.job_id,
        render_backend=request.render.render_backend,
        used_fallback=request.render.used_fallback,
        manifest_location=manifest,
        final_video_location=final_video,
        included_assets=[
            request.render.preview_location.uri if request.render.preview_location else "",
            request.render.spec.output_location.uri,
            manifest.uri,
        ],
    )
    store_bytes(
        manifest,
        json.dumps(package.model_dump(mode="json"), indent=2).encode("utf-8"),
        content_type="application/json",
    )
    return package
