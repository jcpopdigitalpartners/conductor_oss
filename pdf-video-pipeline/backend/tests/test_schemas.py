import json
from io import BytesIO
from uuid import uuid4

from pypdf import PdfWriter

from app.db import init_db
from app.main import (
    apply_review_delta,
    build_creative_brief,
    build_document_profile,
    build_workflow_input,
    build_render_spec,
    build_review_from_uploaded_pdf,
    create_render_job,
    create_review,
    get_document_understanding,
    infer_document_understanding,
    infer_document_understanding_endpoint,
    package_assets,
    parse_document,
    start_conductor_workflow,
    submit_review_decision,
)
from app.repository import get_render as fetch_render, get_review as fetch_review, get_review_packet as fetch_review_packet
from app.schemas import (
    BuildCreativeBriefRequest,
    CreateRenderJobRequest,
    CreateReviewRequest,
    CreateRenderSpecRequest,
    InferDocumentUnderstandingRequest,
    PackageAssetsRequest,
    ParseDocumentRequest,
    ReviewDecision,
    RenderStatus,
    ReviewStatus,
    StorageLocation,
    WorkflowLaunchStatus,
)
from app.storage import load_bytes, store_bytes

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def make_pdf_bytes() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    writer.write(buffer)
    return buffer.getvalue()


def make_render_spec(job_id) -> object:
    source = StorageLocation(
        bucket="raw",
        key=f"jobs/{job_id}/source/sample.pdf",
        uri=f"s3://raw/jobs/{job_id}/source/sample.pdf",
    )
    document = build_document_profile(
        ParseDocumentRequest(
            job_id=job_id,
            filename="sample.pdf",
            source=source,
            page_count=1,
            extracted_text="Hero product overview",
        )
    )
    brief = build_creative_brief(
        BuildCreativeBriefRequest(
            document_understanding=infer_document_understanding(document),
            requested_look_and_feel="hero design",
        )
    ).model_copy(update={"target_duration_seconds": 15})
    return build_render_spec(
        CreateRenderSpecRequest(
            creative_brief=brief,
            review_decision=ReviewDecision(
                review_id=uuid4(),
                job_id=job_id,
                status=ReviewStatus.APPROVED,
                reviewer_id="qa",
            ),
        )
    ).model_copy(update={"fps": 12, "resolution": "320x180"})


def test_uploaded_review_is_persisted_with_html_packet(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "pipeline.sqlite3"
    monkeypatch.setattr("app.db.settings.database_path", str(db_path))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )

    stored_review = fetch_review(review.review_id)
    html_packet = fetch_review_packet(review.review_id)

    assert stored_review is not None
    assert stored_review.review_id == review.review_id
    assert stored_review.packet_url is not None
    assert stored_review.packet_url.endswith(f"/reviews/{review.review_id}/packet")
    assert html_packet is not None
    assert "Human Review Packet" in html_packet
    assert "launch_deck.pdf" in html_packet


def test_document_to_render_spec_happy_path() -> None:
    job_id = uuid4()
    source = StorageLocation(
        bucket="raw",
        key=f"jobs/{job_id}/source/sample.pdf",
        uri=f"s3://raw/jobs/{job_id}/source/sample.pdf",
    )
    document = build_document_profile(
        ParseDocumentRequest(
            job_id=job_id,
            filename="sample.pdf",
            source=source,
            page_count=3,
            extracted_text=(
                "Hero design overview\n"
                "Product platform for healthcare automation\n"
                "Request a demo to accelerate approvals\n"
            ),
        )
    )

    document_understanding = infer_document_understanding(document)
    brief = build_creative_brief(
        BuildCreativeBriefRequest(
            document_understanding=document_understanding,
            requested_look_and_feel="hero design",
        )
    )
    decision = ReviewDecision(
        review_id=uuid4(),
        job_id=job_id,
        status=ReviewStatus.APPROVED,
        reviewer_id="qa",
        edited_look_and_feel_prompt="hero design with product glow",
    )

    updated_brief = apply_review_delta(brief, decision)
    spec = build_render_spec(
        CreateRenderSpecRequest(creative_brief=updated_brief, review_decision=decision)
    )

    assert document_understanding.intent_tone.intent.value == "sell"
    assert updated_brief.look_and_feel_prompt == "hero design with product glow"
    assert spec.model_family == "wan-2.2"
    assert spec.aspect_ratio == "16:9"
    assert "Request a demo to accelerate approvals" in spec.prompt
    assert any("Narration:" in scene_prompt for scene_prompt in spec.scene_prompts)


def test_build_review_from_uploaded_pdf_creates_pending_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )

    assert review.status == ReviewStatus.PENDING
    assert review.requested_by == "review-ui-test"
    assert review.packet_url is not None
    assert review.creative_brief.look_and_feel_prompt == "hero design"
    assert "launch_deck.pdf" in review.creative_brief.summary


def test_build_review_from_uploaded_pdf_persists_document_understanding(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )

    stored_document_understanding = get_document_understanding(review.creative_brief.job_id)

    assert stored_document_understanding is not None
    assert stored_document_understanding.job_id == review.creative_brief.job_id
    assert stored_document_understanding.document.filename == "launch_deck.pdf"


def test_create_review_reuses_existing_review_id(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "pipeline.sqlite3"
    monkeypatch.setattr("app.db.settings.database_path", str(db_path))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    existing_review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )
    updated_brief = existing_review.creative_brief.model_copy(
        update={"look_and_feel_prompt": "hero design with brighter lighting"}
    )

    reused_review = create_review(
        CreateReviewRequest(
            creative_brief=updated_brief,
            requested_by="conductor",
            existing_review_id=existing_review.review_id,
        )
    )

    assert reused_review.review_id == existing_review.review_id
    assert reused_review.requested_by == existing_review.requested_by
    assert reused_review.creative_brief.look_and_feel_prompt == "hero design with brighter lighting"


def test_start_conductor_workflow_marks_review_started(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"wf-12345"

    def fake_urlopen(request, timeout):
        assert timeout == 10
        assert request.full_url.endswith("/workflow")
        return DummyResponse()

    monkeypatch.setattr("app.main.urllib_request.urlopen", fake_urlopen)

    updated = start_conductor_workflow(review)

    workflow_input = build_workflow_input(updated)
    assert workflow_input["existing_review_id"] == str(review.review_id)
    assert workflow_input["filename"] == "launch_deck.pdf"
    assert updated.workflow_id == "wf-12345"
    assert updated.workflow_status == WorkflowLaunchStatus.STARTED


def test_start_conductor_workflow_returns_existing_starting_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    ).model_copy(update={"workflow_status": WorkflowLaunchStatus.STARTING})

    returned = start_conductor_workflow(review)

    assert returned.workflow_status == WorkflowLaunchStatus.STARTING
    assert returned.workflow_id is None


def test_submit_review_decision_completes_waiting_human_task(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "pipeline.sqlite3"
    monkeypatch.setattr("app.db.settings.database_path", str(db_path))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="conductor",
    )
    decision = ReviewDecision(
        review_id=review.review_id,
        job_id=review.creative_brief.job_id,
        status=ReviewStatus.APPROVED,
        reviewer_id="creative.approver",
        reviewer_notes="Ready to render.",
    )

    captured_update_payload: dict[str, object] = {}

    class DummyResponse:
        def __init__(self, payload: str) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._payload.encode("utf-8")

    def fake_urlopen(request, timeout):
        assert timeout == 10
        if request.full_url.endswith("/workflow/running/hitl_style_review"):
            return DummyResponse(json.dumps(["subwf-123"]))
        if request.full_url.endswith("/workflow/subwf-123?includeTasks=true"):
            return DummyResponse(
                json.dumps(
                    {
                        "workflowId": "subwf-123",
                        "tasks": [
                            {
                                "taskType": "HUMAN",
                                "status": "IN_PROGRESS",
                                "taskId": "task-123",
                                "workflowInstanceId": "subwf-123",
                                "inputData": {"review_id": str(review.review_id)},
                            }
                        ],
                    }
                )
            )
        if request.full_url.endswith("/tasks"):
            captured_update_payload.update(json.loads(request.data.decode("utf-8")))
            return DummyResponse(json.dumps({"taskId": "task-123"}))
        raise AssertionError(f"Unexpected Conductor request: {request.full_url}")

    monkeypatch.setattr("app.main.urllib_request.urlopen", fake_urlopen)

    updated = submit_review_decision(review.review_id, decision)
    stored_review = fetch_review(review.review_id)

    assert updated.status == ReviewStatus.APPROVED
    assert stored_review is not None
    assert stored_review.latest_decision is not None
    assert stored_review.latest_decision.status == ReviewStatus.APPROVED
    assert captured_update_payload["workflowInstanceId"] == "subwf-123"
    assert captured_update_payload["taskId"] == "task-123"
    assert captured_update_payload["status"] == "COMPLETED"
    assert captured_update_payload["outputData"]["review_status"] == ReviewStatus.APPROVED.value


def test_submit_review_decision_skips_conductor_for_staged_review(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "pipeline.sqlite3"
    monkeypatch.setattr("app.db.settings.database_path", str(db_path))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    review = build_review_from_uploaded_pdf(
        filename="launch_deck.pdf",
        pdf_bytes=PDF_BYTES,
        requested_look_and_feel="hero design",
        requested_by="review-ui-test",
    )
    decision = ReviewDecision(
        review_id=review.review_id,
        job_id=review.creative_brief.job_id,
        status=ReviewStatus.REJECTED,
        reviewer_id="creative.approver",
        reviewer_notes="Needs a different direction.",
    )

    def fail_urlopen(request, timeout):
        raise AssertionError(f"submit_review_decision should not call Conductor: {request.full_url}")

    monkeypatch.setattr("app.main.urllib_request.urlopen", fail_urlopen)

    updated = submit_review_decision(review.review_id, decision)

    assert updated.status == ReviewStatus.REJECTED
    assert updated.latest_decision is not None
    assert updated.latest_decision.status == ReviewStatus.REJECTED


def test_parse_document_extracts_from_object_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    job_id = uuid4()
    source = StorageLocation(
        bucket="raw",
        key=f"jobs/{job_id}/source/sample.pdf",
        uri=f"s3://raw/jobs/{job_id}/source/sample.pdf",
    )
    store_bytes(source, make_pdf_bytes(), content_type="application/pdf")

    profile = parse_document(
        ParseDocumentRequest(
            job_id=job_id,
            filename="sample.pdf",
            source=source,
            hint_document_type=None,
        )
    )

    assert profile.filename == "sample.pdf"
    assert profile.extracted_text_location is not None
    markdown = load_bytes(profile.extracted_text_location).decode("utf-8")
    assert markdown
    assert profile.parser_used == "pypdf"


def test_infer_document_understanding_endpoint_persists_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    job_id = uuid4()
    source = StorageLocation(
        bucket="raw",
        key=f"jobs/{job_id}/source/sample.pdf",
        uri=f"s3://raw/jobs/{job_id}/source/sample.pdf",
    )
    document = build_document_profile(
        ParseDocumentRequest(
            job_id=job_id,
            filename="sample.pdf",
            source=source,
            page_count=2,
            extracted_text="Product overview with a clear call to action.",
        )
    )

    persisted_document_understanding = infer_document_understanding_endpoint(
        InferDocumentUnderstandingRequest(document=document)
    )
    fetched_document_understanding = get_document_understanding(job_id)

    assert fetched_document_understanding == persisted_document_understanding
    assert fetched_document_understanding.intent_tone.call_to_action


def test_create_render_job_persists_and_completes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    monkeypatch.setattr("app.render.executor.settings.render_dev_fallback_enabled", True)
    monkeypatch.setattr("app.render.executor.settings.comfyui_base_url", "")
    init_db()

    job_id = uuid4()
    spec = make_render_spec(job_id)

    render = create_render_job(CreateRenderJobRequest(spec=spec))
    assert render.status.name.lower() == "queued"

    completed = None
    for _ in range(60):
        completed = fetch_render(render.render_id)
        if completed and completed.status.name.lower() == "completed":
            break
        import time

        time.sleep(0.2)

    assert completed is not None
    assert completed.status.name.lower() == "completed"
    assert completed.final_video_location is not None
    assert load_bytes(completed.final_video_location)


def test_package_assets_writes_manifest_for_completed_render(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.db.settings.database_path", str(tmp_path / "pipeline.sqlite3"))
    monkeypatch.setattr("app.storage.settings.object_store_path", str(tmp_path / "object-store"))
    init_db()

    monkeypatch.setattr("app.main.enqueue_render_job", lambda render_id: None)

    job_id = uuid4()
    render_location = StorageLocation(
        bucket="final",
        key=f"jobs/{job_id}/renders/final.mp4",
        uri=f"s3://final/jobs/{job_id}/renders/final.mp4",
    )
    store_bytes(render_location, b"fake-mp4", content_type="video/mp4")

    render = fetch_render(
        create_render_job(
            CreateRenderJobRequest(spec=make_render_spec(job_id).model_copy(update={"output_location": render_location}))
        ).render_id
    )

    assert render is not None
    render = render.model_copy(update={"status": RenderStatus.COMPLETED, "final_video_location": render_location})
    from app.repository import save_render

    save_render(render)

    package = package_assets(
        PackageAssetsRequest(
            job_id=render.spec.job_id,
            render=render,
            review_decision=ReviewDecision(
                review_id=uuid4(),
                job_id=render.spec.job_id,
                status=ReviewStatus.APPROVED,
                reviewer_id="qa",
            ),
        )
    )

    manifest_bytes = load_bytes(package.manifest_location)
    assert package.final_video_location == render_location
    assert b"manifest_location" in manifest_bytes
