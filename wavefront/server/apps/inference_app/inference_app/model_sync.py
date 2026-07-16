"""Sync Hugging Face-style model folders from cloud blob storage to a local cache.

Mirrors the pattern in packages/utility/utility/model_resolver.py but is
self-contained inside inference_app so it has no cross-repo dependency.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger

_CLOUD_URI_PATTERN = re.compile(
    r"^(?:gs://|s3://|azure://).+",
    re.IGNORECASE,
)

CLOUD_PROVIDER = os.getenv("CLOUD_PROVIDER", "")
CLIP_MODEL_URI = os.getenv("CLIP_MODEL_URI", "")
DINO_MODEL_URI = os.getenv("DINO_MODEL_URI", "")
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/tmp/model-cache")


def is_cloud_uri(uri: str) -> bool:
    """Return True if *uri* is a supported cloud storage URI (gs://, s3://, azure://)."""
    return bool(_CLOUD_URI_PATTERN.match(uri.strip()))


def _cache_key(uri: str) -> str:
    return hashlib.sha256(uri.strip().encode()).hexdigest()[:16]


def _list_all_keys(
    storage: CloudStorageManager,
    bucket_name: str,
    prefix: str,
    *,
    page_size: int = 100,
) -> list[str]:
    keys: list[str] = []
    page_number = 1
    while True:
        batch, has_next = storage.list_files(
            bucket_name, prefix, page_size=page_size, page_number=page_number
        )
        keys.extend(batch)
        if not has_next:
            break
        page_number += 1
    return keys


def sync_cloud_model(uri: str, *, provider: str, cache_root: Path) -> Path:
    """
    Download all objects under a cloud URI prefix into a local cache directory.

    Skips download if a .sync_complete marker already exists (cache hit).

    Args:
        uri: Cloud URI (gs://, s3://, or azure://container/prefix/).
        provider: Cloud provider string passed to CloudStorageManager (gcp, aws, azure).
        cache_root: Parent directory for cached model folders.

    Returns:
        Path to the local directory containing the synced model files.

    Raises:
        ValueError: If *uri* is not a cloud URI or the prefix lists no objects.
    """
    uri = uri.strip()
    if not is_cloud_uri(uri):
        raise ValueError(
            f"Model URI must be a cloud URI (gs://, s3://, or azure://); got {uri!r}"
        )

    storage = CloudStorageManager(provider)
    bucket_name, prefix = storage.get_bucket_key(uri)
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"

    dest_dir = cache_root / _cache_key(uri)
    marker = dest_dir / ".sync_complete"
    if marker.is_file():
        logger.info("Using cached model at %s (uri=%s)", dest_dir, uri)
        return dest_dir

    logger.info(
        "Syncing model from %s (bucket=%s, prefix=%s) -> %s",
        uri,
        bucket_name,
        prefix,
        dest_dir,
    )

    keys = _list_all_keys(storage, bucket_name, prefix)
    if not keys:
        raise ValueError(f"No objects found at cloud URI {uri!r}")

    for key in keys:
        if key.endswith("/"):
            continue
        relative = key[len(prefix):] if prefix and key.startswith(prefix) else key
        if not relative:
            continue
        local_path = dest_dir / relative
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(storage.read_file(bucket_name, key))
        logger.debug("Downloaded %s", relative)

    marker.write_text(uri, encoding="utf-8")
    logger.info("Synced %d object(s) to %s", len(keys), dest_dir)
    return dest_dir


def _require_cloud_uri(name: str, uri: str) -> str:
    if not uri:
        raise ValueError(f"{name} env var is required but not set")
    if not is_cloud_uri(uri):
        raise ValueError(
            f"{name} must be a cloud URI (gs://, s3://, or azure://); got {uri!r}"
        )
    return uri


def _validate_cloud_config() -> None:
    if not CLOUD_PROVIDER:
        raise ValueError("CLOUD_PROVIDER env var is required but not set")
    _require_cloud_uri("CLIP_MODEL_URI", CLIP_MODEL_URI)
    _require_cloud_uri("DINO_MODEL_URI", DINO_MODEL_URI)


def _ensure_cache_dir() -> Path:
    cache_root = Path(MODEL_CACHE_DIR)
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def _sync_clip(cache_root: Path) -> Path:
    return sync_cloud_model(CLIP_MODEL_URI, provider=CLOUD_PROVIDER, cache_root=cache_root)


def _sync_dino(cache_root: Path) -> Path:
    return sync_cloud_model(DINO_MODEL_URI, provider=CLOUD_PROVIDER, cache_root=cache_root)


def sync_embedding_models() -> tuple[Path, Path]:
    """
    Validate env vars, ensure cache dir, and sync CLIP + DINO from cloud storage.

    Returns:
        (clip_model_dir, dino_model_dir) — local synced directories ready for
        from_pretrained().

    Raises:
        ValueError: If required env vars are missing or not valid cloud URIs.
    """
    _validate_cloud_config()
    cache_root = _ensure_cache_dir()
    clip_dir = _sync_clip(cache_root)
    dino_dir = _sync_dino(cache_root)
    return clip_dir, dino_dir
