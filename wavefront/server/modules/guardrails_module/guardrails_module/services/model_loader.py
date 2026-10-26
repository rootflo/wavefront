"""Model loader for Guardrails spaCy models in Wavefront server.

Downloads and extracts spaCy model archives (.tar.gz) from cloud storage
(S3, GCS, Azure Blob via flo_cloud), HTTP/HTTPS or a local path into a cache
directory, with a file lock so concurrent workers download only once.
"""

from __future__ import annotations

import fcntl
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile
from typing import Optional, Union
from urllib.parse import urlparse

from common_module.log.logger import logger
import flo_lib.http as http

# Pre-installed packages tried, in order, when no model URL is configured
DEFAULT_MODEL_PACKAGES = ('en_core_web_lg', 'en_core_web_sm', 'en_core_web_md')

_SYNC_MARKER = '.sync_complete'
_CLOUD_SCHEMES = ('s3', 'gs', 'azure')

PathLike = Union[str, Path]


def resolve_spacy_model_dir(extracted_root: Path) -> Path:
    """Find the directory containing config.cfg in an extracted spaCy model."""
    if (extracted_root / 'config.cfg').is_file():
        return extracted_root
    for config_path in extracted_root.rglob('config.cfg'):
        return config_path.parent
    raise FileNotFoundError(
        f"Invalid spaCy model archive: config.cfg not found anywhere inside '{extracted_root}'."
    )


def _cached_model(path: Path) -> Optional[Path]:
    """The model directory inside ``path`` if it is a complete download."""
    if not (path / _SYNC_MARKER).is_file():
        return None
    try:
        return resolve_spacy_model_dir(path)
    except FileNotFoundError:
        return None


def extract_tar_archive(archive_path: Path, target_dir: Path) -> Path:
    """Safely extract a .tar.gz archive to target_dir and resolve the model directory."""
    if not hasattr(tarfile, 'data_filter'):
        raise RuntimeError('Extracting model archives safely needs Python >= 3.11.4')
    logger.info("Extracting '%s' to '%s'", archive_path.name, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, 'r:*') as tar:
        # Rejects links, special files and paths outside target_dir
        tar.extractall(path=target_dir, filter='data')
    return resolve_spacy_model_dir(target_dir)


def _resolve_cache_root(cache_dir: Optional[PathLike]) -> Path:
    """The first writable cache directory: ``cache_dir``, then user cache, then tmp."""
    candidates = [Path(cache_dir)] if cache_dir else []
    candidates += [
        Path.home() / '.cache' / 'wavefront' / 'spacy',
        Path(tempfile.gettempdir()) / 'wavefront_spacy',
    ]
    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            tempfile.TemporaryFile(dir=root).close()
            return root
        except OSError as exc:
            logger.warning("Cache directory '%s' is not writable (%s)", root, exc)
    raise RuntimeError('No writable cache directory for spaCy models')


def get_model_cache_dir_name(url: str) -> str:
    """Derive deterministic cache directory name from model URL."""
    url = url.strip()
    url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    name = Path(urlparse(url).path).name
    for suffix in ('.tar.gz', '.tgz', '.tar'):
        name = name.removesuffix(suffix)
    return f"{name.replace('.', '_') or 'model'}_{url_hash}"


def _download_stream_http(url: str, dest_path: Path, timeout_s: int = 120) -> None:
    """Stream download over HTTP/HTTPS in 1MB chunks."""
    with http.create_client(
        timeout=timeout_s,
        follow_redirects=True,
        headers={'User-Agent': 'Wavefront-ModelLoader/1.0'},
    ) as client, client.stream('GET', url) as response, open(dest_path, 'wb') as f:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
            f.write(chunk)


def download_file(url: str, dest_path: Path) -> None:
    """Download model archive (.tar.gz) from S3, GCS, Azure, HTTP/HTTPS, or local file."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    url = url.strip()
    scheme = urlparse(url).scheme.lower()
    logger.info("Downloading spaCy model archive from '%s'", url)

    if scheme in _CLOUD_SCHEMES:
        from flo_cloud._types import CloudProvider
        from flo_cloud.cloud_storage import CloudStorageManager

        provider = {
            's3': CloudProvider.AWS,
            'gs': CloudProvider.GCP,
            'azure': CloudProvider.AZURE,
        }[scheme]
        storage = CloudStorageManager(provider)
        bucket, key = storage.get_bucket_key(url)
        storage.download_to_file(bucket, key, dest_path)
    elif scheme in ('http', 'https'):
        _download_stream_http(url, dest_path)
    elif scheme in ('file', ''):
        local_src = Path(urlparse(url).path if scheme == 'file' else url)
        if not local_src.is_file():
            raise FileNotFoundError(f'Local file not found: {local_src}')
        shutil.copy2(local_src, dest_path)
    else:
        raise ValueError(f'Unsupported URL scheme {scheme!r} in model URL: {url!r}')

    logger.info('Download completed: %.2f MB', dest_path.stat().st_size / (1024 * 1024))


def _find_named_model(model_name: str, cache_dir: Optional[PathLike]) -> Optional[str]:
    """``model_name`` as an installed package, a model directory or a completed
    cache entry."""
    import spacy.util

    if spacy.util.is_package(model_name):
        return model_name
    local = Path(model_name)
    if local.is_dir():
        try:
            return str(resolve_spacy_model_dir(local))
        except FileNotFoundError:
            pass
    if cache_dir and (cached := _cached_model(Path(cache_dir) / model_name)):
        return str(cached)
    return None


def _find_default_package() -> Optional[str]:
    import spacy.util

    return next((p for p in DEFAULT_MODEL_PACKAGES if spacy.util.is_package(p)), None)


def ensure_spacy_model(
    model_url: Optional[str] = None,
    cache_dir: Optional[PathLike] = None,
    model_name: Optional[str] = None,
) -> str:
    """Return a spaCy model name or path, downloading ``model_url`` into the
    cache when it is not there yet."""
    if model_name and (named := _find_named_model(model_name, cache_dir)):
        return named
    url = (model_url or '').strip()
    if not url:
        if package := _find_default_package():
            return package
        raise RuntimeError(
            'spaCy model URL is not configured and no pre-installed model was found. '
            'Configure [guardrails] spacy_model_url or install en_core_web_lg.'
        )

    dir_name = get_model_cache_dir_name(url)
    # The configured cache may be read-only yet already hold the model
    if cache_dir and (cached := _cached_model(Path(cache_dir) / dir_name)):
        return str(cached)

    cache_root = _resolve_cache_root(cache_dir)
    target_dir = cache_root / dir_name
    # flock serialises workers (and threads: each call opens its own lock file)
    with open(cache_root / f'.{dir_name}.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if cached := _cached_model(target_dir):
            return str(cached)

        with tempfile.TemporaryDirectory(dir=cache_root, prefix='.staging_') as tmp:
            staging_dir = Path(tmp) / 'model'
            archive = Path(tmp) / 'model.tar.gz'
            download_file(url, archive)
            extract_tar_archive(archive, staging_dir)
            shutil.rmtree(target_dir, ignore_errors=True)
            staging_dir.rename(target_dir)

        (target_dir / _SYNC_MARKER).write_text(f'source={url}\n', encoding='utf-8')
        resolved = resolve_spacy_model_dir(target_dir)
        logger.info('spaCy model cached at %s', resolved)
        return str(resolved)


def is_spacy_model_available(
    model_url: Optional[str] = None,
    cache_dir: Optional[PathLike] = None,
    model_name: Optional[str] = None,
) -> bool:
    """Whether a spaCy model can be resolved (via URL, cache, or pre-installed package)."""
    if model_url and model_url.strip():
        return True
    try:
        if model_name and _find_named_model(model_name, cache_dir):
            return True
        return _find_default_package() is not None
    except ImportError:
        return False
