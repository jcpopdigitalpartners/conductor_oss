from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from .config import settings
from .db import get_connection
from .review_packet import render_review_packet
from .schemas import (
    DocumentUnderstanding,
    DocumentProfile,
    IngestResponse,
    RenderJob,
    ReviewRecord,
    ReviewStatus,
)


def save_ingest(ingest: IngestResponse) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO ingests (job_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                str(ingest.job_id),
                ingest.model_dump_json(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def save_document(document: DocumentProfile) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO documents (job_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                str(document.job_id),
                document.model_dump_json(),
                document.created_at.isoformat(),
            ),
        )


def get_document(job_id: UUID) -> DocumentProfile | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM documents WHERE job_id = ?",
            (str(job_id),),
        ).fetchone()
    if row is None:
        return None
    return DocumentProfile.model_validate_json(row["payload_json"])


def save_document_understanding(document_understanding: DocumentUnderstanding) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO document_understandings (job_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                str(document_understanding.job_id),
                document_understanding.model_dump_json(),
                document_understanding.created_at.isoformat(),
            ),
        )


def get_document_understanding(job_id: UUID) -> DocumentUnderstanding | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM document_understandings WHERE job_id = ?",
            (str(job_id),),
        ).fetchone()
    if row is None:
        return None
    return DocumentUnderstanding.model_validate_json(row["payload_json"])


def save_review(review: ReviewRecord, document: DocumentProfile) -> ReviewRecord:
    persisted_review = review.model_copy(
        update={
            "packet_url": review.packet_url
            or f"{settings.api_base_url.rstrip('/')}/reviews/{review.review_id}/packet"
        }
    )
    html_packet = render_review_packet(persisted_review, document)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reviews
            (review_id, job_id, status, workflow_status, payload_json, html_packet, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(persisted_review.review_id),
                str(persisted_review.creative_brief.job_id),
                persisted_review.status.value,
                persisted_review.workflow_status.value,
                persisted_review.model_dump_json(),
                html_packet,
                persisted_review.created_at.isoformat(),
            ),
        )
    return persisted_review


def get_review(review_id: UUID) -> ReviewRecord | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM reviews WHERE review_id = ?",
            (str(review_id),),
        ).fetchone()
    if row is None:
        return None
    return ReviewRecord.model_validate_json(row["payload_json"])


def get_review_packet(review_id: UUID) -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT html_packet FROM reviews WHERE review_id = ?",
            (str(review_id),),
        ).fetchone()
    if row is None:
        return None
    return row["html_packet"]


def save_render(render: RenderJob) -> RenderJob:
    persisted_render = render.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO renders
            (render_id, job_id, status, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(persisted_render.render_id),
                str(persisted_render.spec.job_id),
                persisted_render.status.value,
                persisted_render.model_dump_json(),
                persisted_render.created_at.isoformat(),
                persisted_render.updated_at.isoformat(),
            ),
        )
    return persisted_render


def get_render(render_id: UUID) -> RenderJob | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM renders WHERE render_id = ?",
            (str(render_id),),
        ).fetchone()
    if row is None:
        return None
    return RenderJob.model_validate_json(row["payload_json"])


def list_reviews(status: ReviewStatus | None = None) -> list[ReviewRecord]:
    query = "SELECT payload_json FROM reviews"
    params: tuple[str, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status.value,)
    query += " ORDER BY created_at DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [ReviewRecord.model_validate_json(row["payload_json"]) for row in rows]


def persist_review_update(review: ReviewRecord) -> ReviewRecord:
    document = get_document(review.creative_brief.job_id)
    if document is None:
        raise ValueError("Cannot persist review without source document")
    return save_review(review, document)


def bootstrap_storage(
    ingest: IngestResponse,
    document: DocumentProfile,
    document_understanding: DocumentUnderstanding | None,
    review: ReviewRecord,
) -> ReviewRecord:
    save_ingest(ingest)
    save_document(document)
    if document_understanding is not None:
        save_document_understanding(document_understanding)
    return save_review(review, document)
