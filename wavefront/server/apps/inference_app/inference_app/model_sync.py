"""Resolve and sync model directories for CLIP and DINOv3.

Each model source (CLIP_VIT_BASE_PATCH32_MODEL_URI, DINOV3_VITL16_HF_MODEL_URI) can be:
- A cloud URI (gs://, s3://, azure://) — synced to MODEL_CACHE_DIR on startup.
- A local directory path — used directly with no download.

Cloud sync is skipped when a .sync_complete marker exists in the cache dir.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger

from inference_app.env import (
    CLOUD_PROVIDER,
    CLIP_VIT_BASE_PATCH32_MODEL_URI,
    DINOV3_VITL16_HF_MODEL_URI,
    MODEL_CACHE_DIR,
)

_CLOUD_URI_PATTERN = re.compile(
    r"^(?:gs://|s3://|azure://).+",
    re.IGNORECASE,
)


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


def resolve_model_dir(name: str, uri: str, cache_root: Path) -> Path:
    """
    Resolve a model source to a local directory.

    Accepts:
    - Cloud URI (gs://, s3://, azure://) — downloads to cache_root and returns
      the local dir. Skips download if .sync_complete already exists.
    - Local directory path — returned directly with no download.

    Args:
        name: Env var name, used in error messages.
        uri: Cloud URI or local path string.
        cache_root: Parent directory for synced model folders (used for cloud only).

    Returns:
        Path to a local directory ready for from_pretrained().

    Raises:
        ValueError: If uri is empty, not a cloud URI, and not an existing local dir.
    """
    if not uri:
        raise ValueError(f"{name} env var is required but not set")

    if is_cloud_uri(uri):
        if not CLOUD_PROVIDER:
            raise ValueError(
                "CLOUD_PROVIDER env var is required when using a cloud URI"
            )
        return sync_cloud_model(uri, provider=CLOUD_PROVIDER, cache_root=cache_root)

    local = Path(uri)
    if local.is_dir():
        logger.info("Using local model dir for %s: %s", name, local)
        return local

    raise ValueError(
        f"{name}={uri!r} is neither a cloud URI (gs://, s3://, azure://)"
        f" nor an existing local directory"
    )


def _ensure_cache_dir() -> Path:
    cache_root = Path(MODEL_CACHE_DIR)
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def sync_embedding_models() -> tuple[Path, Path]:
    """
    Resolve CLIP and DINO model directories from env vars.

    Each URI can be a cloud URI (gs://, s3://, azure://) or a local directory path.
    Cloud sources are synced to MODEL_CACHE_DIR; local paths are used directly.

    Returns:
        (clip_model_dir, dino_model_dir) — local directories ready for from_pretrained().

    Raises:
        ValueError: If required env vars are missing or point to invalid sources.
    """
    cache_root = _ensure_cache_dir()
    clip_dir = resolve_model_dir("CLIP_VIT_BASE_PATCH32_MODEL_URI", CLIP_VIT_BASE_PATCH32_MODEL_URI, cache_root)
    dino_dir = resolve_model_dir("DINOV3_VITL16_HF_MODEL_URI", DINOV3_VITL16_HF_MODEL_URI, cache_root)
    return clip_dir, dino_dir
