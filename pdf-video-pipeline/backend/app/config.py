from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    service_name: str = "pdf-video-pipeline-backend"
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    conductor_base_url: str = os.getenv("CONDUCTOR_BASE_URL", "http://localhost:8080/api")
    database_path: str = os.getenv("DATABASE_PATH", "./data/pdf_video_pipeline.sqlite3")
    object_store_path: str = os.getenv("OBJECT_STORE_PATH", "./data/object_store")
    minio_enabled: bool = os.getenv("MINIO_ENABLED", "false").lower() == "true"
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    minio_bucket_raw: str = os.getenv("MINIO_BUCKET_RAW", "raw")
    minio_bucket_parsed: str = os.getenv("MINIO_BUCKET_PARSED", "parsed")
    minio_bucket_reviews: str = os.getenv("MINIO_BUCKET_REVIEWS", "reviews")
    minio_bucket_renders: str = os.getenv("MINIO_BUCKET_RENDERS", "renders")
    minio_bucket_final: str = os.getenv("MINIO_BUCKET_FINAL", "final")
    default_aspect_ratio: str = os.getenv("DEFAULT_ASPECT_RATIO", "16:9")
    default_resolution: str = os.getenv("DEFAULT_RESOLUTION", "1920x1080")
    default_duration_seconds: int = int(os.getenv("DEFAULT_DURATION_SECONDS", "45"))
    default_fps: int = int(os.getenv("DEFAULT_FPS", "24"))
    primary_video_model: str = os.getenv("PRIMARY_VIDEO_MODEL", "wan-2.2")
    fallback_video_model: str = os.getenv("FALLBACK_VIDEO_MODEL", "cogvideox")
    comfyui_base_url: str = os.getenv("COMFYUI_BASE_URL", "").rstrip("/")
    comfyui_workflow_template_path: str = os.getenv("COMFYUI_WORKFLOW_TEMPLATE_PATH", "")
    render_poll_interval_seconds: int = int(os.getenv("RENDER_POLL_INTERVAL_SECONDS", "5"))
    render_timeout_seconds: int = int(os.getenv("RENDER_TIMEOUT_SECONDS", "900"))
    render_wait_duration: str = os.getenv("RENDER_WAIT_DURATION", "10 seconds")
    render_dev_fallback_enabled: bool = os.getenv("RENDER_DEV_FALLBACK_ENABLED", "true").lower() == "true"
    conductor_workflow_name: str = os.getenv("CONDUCTOR_WORKFLOW_NAME", "pdf_to_video_pipeline")
    conductor_workflow_version: int = int(os.getenv("CONDUCTOR_WORKFLOW_VERSION", "1"))


settings = Settings()
