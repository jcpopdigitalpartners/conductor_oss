from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from .schemas import DocumentProfile, IngestResponse, RenderJob, ReviewRecord


@dataclass
class AppState:
    ingests: dict[UUID, IngestResponse] = field(default_factory=dict)
    documents: dict[UUID, DocumentProfile] = field(default_factory=dict)
    reviews: dict[UUID, ReviewRecord] = field(default_factory=dict)
    renders: dict[UUID, RenderJob] = field(default_factory=dict)


app_state = AppState()
