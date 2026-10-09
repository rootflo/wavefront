"""Resolve and sync model directories for CLIP and DINOv3.

Each model source (clip / dino / bge-m3 URI) can be:
- A cloud URI for the configured platform (``gs://``, ``s3://``, or ``azure://``)
  — synced to cache_dir on startup.
- A local directory path — used directly with no download.

Cloud sync is skipped when a .sync_complete marker exists in the cache dir.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger


def is_cloud_uri(uri: str, *, provider: str) -> bool:
    """True if *uri* uses the scheme for the configured cloud *provider*."""
    protocol = CloudStorageManager.protocol_for(provider)
    if not protocol:
        return False
    return uri.strip().lower().startswith(f'{protocol}://')


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
        uri: Cloud URI for *provider* (e.g. ``gs://bucket/prefix/`` on GCP).
        provider: Cloud platform passed to CloudStorageManager (gcp, aws, azure).
        cache_root: Parent directory for cached model folders.

    Returns:
        Path to the local directory containing the synced model files.

    Raises:
        ValueError: If *uri* is not a cloud URI for *provider*, or lists no objects.
    """
    uri = uri.strip()
    protocol = CloudStorageManager.protocol_for(provider)
    if not protocol or not is_cloud_uri(uri, provider=provider):
        expected = f'{protocol}://' if protocol else 'the configured cloud platform'
        raise ValueError(f'Model URI must use {expected}; got {uri!r}')

    storage = CloudStorageManager(provider)
    bucket_name, prefix = storage.get_bucket_key(uri)
    if prefix and not prefix.endswith('/'):
        prefix = f'{prefix}/'

    dest_dir = cache_root / _cache_key(uri)
    marker = dest_dir / '.sync_complete'
    if marker.is_file():
        logger.info('Using cached model at %s (uri=%s)', dest_dir, uri)
        return dest_dir

    logger.info(
        'Syncing model from %s (bucket=%s, prefix=%s) -> %s',
        uri,
        bucket_name,
        prefix,
        dest_dir,
    )

    keys = _list_all_keys(storage, bucket_name, prefix)
    if not keys:
        raise ValueError(f'No objects found at cloud URI {uri!r}')

    for key in keys:
        if key.endswith('/'):
            continue
        relative = key[len(prefix) :] if prefix and key.startswith(prefix) else key
        if not relative:
            continue
        local_path = dest_dir / relative
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(storage.read_file(bucket_name, key))
        logger.debug('Downloaded %s', relative)

    marker.write_text(uri, encoding='utf-8')
    logger.info('Synced %d object(s) to %s', len(keys), dest_dir)
    return dest_dir


def resolve_model_dir(
    name: str,
    uri: str,
    cache_root: Path,
    *,
    cloud_provider: str,
) -> Path:
    """
    Resolve a model source to a local directory.

    Accepts:
    - Cloud URI for *cloud_provider* — downloads to cache_root and returns
      the local dir. Skips download if .sync_complete already exists.
    - Local directory path — returned directly with no download.

    Args:
        name: Config key name, used in error messages.
        uri: Cloud URI or local path string.
        cache_root: Parent directory for synced model folders (used for cloud only).
        cloud_provider: Required when *uri* is a cloud URI (``config.cloud.platform``).

    Returns:
        Path to a local directory ready for from_pretrained().

    Raises:
        ValueError: If uri is empty, not a cloud URI for the platform, and not
            an existing local dir.
    """
    if not uri:
        raise ValueError(f'{name} is required but not set')

    if is_cloud_uri(uri, provider=cloud_provider):
        return sync_cloud_model(uri, provider=cloud_provider, cache_root=cache_root)

    local = Path(uri)
    if local.is_dir():
        logger.info('Using local model dir for %s: %s', name, local)
        return local

    protocol = CloudStorageManager.protocol_for(cloud_provider)
    cloud_hint = (
        f'a {protocol}:// cloud URI' if protocol else 'a cloud URI for cloud.platform'
    )
    raise ValueError(
        f'{name}={uri!r} is neither {cloud_hint} nor an existing local directory'
    )


def _ensure_cache_dir(cache_dir: str) -> Path:
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def sync_embedding_models(
    *,
    clip_uri: str,
    dino_uri: str,
    cache_dir: str,
    cloud_provider: str,
) -> tuple[Path, Path]:
    """
    Resolve CLIP and DINO model directories from config.

    Each URI can be a cloud URI for *cloud_provider* or a local directory path.
    Cloud sources are synced to cache_dir; local paths are used directly.

    Returns:
        (clip_model_dir, dino_model_dir) — local directories ready for from_pretrained().

    Raises:
        ValueError: If required URIs are missing or point to invalid sources.
    """
    cache_root = _ensure_cache_dir(cache_dir)
    clip_dir = resolve_model_dir(
        'models.clip_vit_base_patch32_uri',
        clip_uri,
        cache_root,
        cloud_provider=cloud_provider,
    )
    dino_dir = resolve_model_dir(
        'models.dinov3_vitl16_uri',
        dino_uri,
        cache_root,
        cloud_provider=cloud_provider,
    )
    return clip_dir, dino_dir


def sync_text_embedding_model(
    *,
    bge_m3_uri: str,
    cache_dir: str,
    cloud_provider: str,
) -> Path:
    """
    Resolve the BGE-M3 model directory from models.bge_m3_uri (cloud URI or
    local directory, as for the image models).

    Callers should check bge_m3_uri first: the model is optional.

    Raises:
        ValueError: If bge_m3_uri is unset or points to an invalid source.
    """
    return resolve_model_dir(
        'models.bge_m3_uri',
        bge_m3_uri,
        _ensure_cache_dir(cache_dir),
        cloud_provider=cloud_provider,
    )
