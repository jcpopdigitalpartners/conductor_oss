from __future__ import annotations

from io import BytesIO
from pathlib import Path

from .config import settings
from .schemas import StorageLocation

try:
    from minio import Minio
except ImportError:  # pragma: no cover - exercised via fallback mode
    Minio = None  # type: ignore[assignment]


def _local_object_path(location: StorageLocation) -> Path:
    return Path(settings.object_store_path) / location.bucket / location.key


def _minio_client() -> Minio | None:
    if Minio is None or not settings.minio_enabled or not settings.minio_endpoint:
        return None
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def store_bytes(
    location: StorageLocation,
    payload: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> StorageLocation:
    client = _minio_client()
    if client is not None:
        try:
            _ensure_bucket(client, location.bucket)
            client.put_object(
                location.bucket,
                location.key,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type,
            )
            return location
        except Exception:
            # Fall through to the local object store so local development still works.
            pass

    object_path = _local_object_path(location)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(payload)
    return location


def load_bytes(location: StorageLocation) -> bytes:
    client = _minio_client()
    if client is not None:
        try:
            response = client.get_object(location.bucket, location.key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception:
            pass

    object_path = _local_object_path(location)
    return object_path.read_bytes()
