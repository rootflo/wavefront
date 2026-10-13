"""Model loader for Guardrails spaCy models in Wavefront server.

Downloads, verifies, and extracts spaCy model archives (.tar.gz) from cloud storage
(S3, GCS, Azure Blob via flo_cloud) or HTTP/HTTPS into a local directory with atomic
disk-caching and multi-worker process locking.
"""

from __future__ import annotations

import fcntl
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile
import threading
from typing import Optional, Union
from urllib.parse import urlparse
import urllib.request

from common_module.log.logger import logger

_DOWNLOAD_LOCK = threading.Lock()


def _is_safe_extraction_path(base_dir: Path, target_path: Path) -> bool:
    """Prevent directory traversal attacks during archive extraction."""
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def resolve_spacy_model_dir(extracted_root: Path) -> Path:
    """Find the directory containing config.cfg in an extracted spaCy model."""
    if (extracted_root / 'config.cfg').is_file():
        return extracted_root

    for config_path in extracted_root.rglob('config.cfg'):
        if config_path.is_file():
            return config_path.parent

    raise FileNotFoundError(
        f"Invalid spaCy model archive: config.cfg not found anywhere inside '{extracted_root}'."
    )


def extract_tar_archive(archive_path: Path, target_dir: Path) -> Path:
    """Safely extract a .tar.gz archive to target_dir and resolve the model directory."""
    target_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, 'r:*') as tar:
        if hasattr(tarfile, 'data_filter'):
            tar.extractall(path=target_dir, filter='data')
        else:
            for member in tar.getmembers():
                if member.islnk() or member.issym():
                    raise ValueError(f'Archive link detected in member: {member.name}')
                if not (member.isreg() or member.isdir()):
                    raise ValueError(
                        f'Special file type detected in archive member: {member.name}'
                    )
                dest = target_dir / member.name
                if not _is_safe_extraction_path(target_dir, dest):
                    raise ValueError(
                        f'Path traversal detected in archive member: {member.name}'
                    )
            tar.extractall(path=target_dir)

    return resolve_spacy_model_dir(target_dir)


def _resolve_cache_root(cache_dir: Optional[Union[str, Path]]) -> Path:
    """Resolve and verify cache root directory with multi-tier fallback."""
    candidates: list[Path] = []
    if cache_dir is not None and str(cache_dir).strip():
        candidates.append(Path(cache_dir))
    candidates.append(Path.home() / '.cache' / 'wavefront' / 'spacy')
    candidates.append(Path(tempfile.gettempdir()) / 'wavefront_spacy')

    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / f'.probe_write_{Path(__file__).stem}'
            probe.touch()
            probe.unlink(missing_ok=True)
            return root
        except (PermissionError, OSError) as exc:
            logger.warning(
                "Cache directory '%s' is not writable (%s). Attempting fallback directory...",
                root,
                exc,
            )
            continue

    fallback = Path(tempfile.gettempdir()) / 'wavefront_spacy'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_model_cache_dir_name(url: str) -> str:
    """Derive deterministic cache directory name from model URL."""
    url_clean = url.strip()
    url_hash = hashlib.sha256(url_clean.encode('utf-8')).hexdigest()[:16]
    path_suffix = Path(urlparse(url_clean).path).name
    clean_suffix = (
        path_suffix.replace('.tar.gz', '')
        .replace('.tgz', '')
        .replace('.tar', '')
        .replace('.', '_')
    )
    if clean_suffix:
        return f'{clean_suffix}_{url_hash}'
    return f'model_{url_hash}'


def _download_stream_http(url: str, dest_path: Path, timeout_s: int = 120) -> None:
    """Stream download over HTTP/HTTPS in 1MB chunks."""
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Wavefront-ModelLoader/1.0'}
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as response, open(
        dest_path, 'wb'
    ) as f:
        shutil.copyfileobj(response, f, length=1024 * 1024)


def download_file(url: str, dest_path: Path) -> None:
    """Download model archive (.tar.gz) from S3, GCS, Azure, HTTP/HTTPS, or local file."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    url_clean = url.strip()
    scheme = urlparse(url_clean).scheme.lower()

    if scheme in ('s3', 'gs', 'azure'):
        from flo_cloud._types import CloudProvider
        from flo_cloud.cloud_storage import CloudStorageManager

        provider_map = {
            's3': CloudProvider.AWS,
            'gs': CloudProvider.GCP,
            'azure': CloudProvider.AZURE,
        }
        provider = provider_map[scheme]
        storage = CloudStorageManager(provider)
        bucket, key = storage.get_bucket_key(url_clean)

        if scheme == 's3':
            storage.handler.s3_client.download_file(bucket, key, str(dest_path))
        elif scheme == 'gs':
            storage.handler.client.bucket(bucket).blob(key).download_to_filename(
                str(dest_path)
            )
        elif scheme == 'azure':
            blob_client = storage.handler.client.get_blob_client(
                container=bucket, blob=key
            )
            with open(dest_path, 'wb') as f:
                blob_client.download_blob().readinto(f)
    elif scheme in ('http', 'https'):
        _download_stream_http(url_clean, dest_path)
    elif scheme == 'file' or not scheme or Path(url_clean).exists():
        local_src = Path(urlparse(url_clean).path if scheme == 'file' else url_clean)
        if not local_src.exists():
            raise FileNotFoundError(f'Local file not found: {local_src}')
        shutil.copy2(local_src, dest_path)
    else:
        raise ValueError(f'Unsupported URL scheme {scheme!r} in model URL: {url!r}')


def ensure_spacy_model(
    model_url: Optional[str] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    model_name: Optional[str] = None,
) -> str:
    """Resolve or download spaCy model archive (.tar.gz) to local cache and return directory path."""
    import spacy.util

    cache_root = _resolve_cache_root(cache_dir)
    effective_url = (model_url or '').strip()

    # 1. Check if model_name was explicitly passed and is an installed package or directory
    if model_name:
        if spacy.util.is_package(model_name):
            logger.debug("spaCy model '%s' is an installed Python package", model_name)
            return model_name
        candidate_name_path = Path(model_name)
        if (
            candidate_name_path.is_dir()
            and (resolve_spacy_model_dir(candidate_name_path) / 'config.cfg').is_file()
        ):
            return str(resolve_spacy_model_dir(candidate_name_path))
        named_cache = cache_root / model_name
        if named_cache.is_dir() and (named_cache / '.sync_complete').is_file():
            resolved = resolve_spacy_model_dir(named_cache)
            if (resolved / 'config.cfg').is_file():
                logger.debug('Using cached spaCy model at %s', resolved)
                return str(resolved)
        if not effective_url:
            raise RuntimeError(
                f"spaCy model '{model_name}' was requested but not found in installed packages or cache, "
                'and spacy_model_url is not configured.'
            )

    # 2. If no URL is provided, check existing cache root and installed packages
    if not effective_url:
        if cache_root.is_dir():
            for child in sorted(cache_root.iterdir()):
                if child.is_dir() and (child / '.sync_complete').is_file():
                    resolved = resolve_spacy_model_dir(child)
                    if (resolved / 'config.cfg').is_file():
                        logger.debug(
                            'Found cached fallback spaCy model at %s', resolved
                        )
                        return str(resolved)

        for candidate in ('en_core_web_lg', 'en_core_web_sm', 'en_core_web_md'):
            if spacy.util.is_package(candidate):
                logger.debug("Found pre-installed fallback spaCy model '%s'", candidate)
                return candidate

        raise RuntimeError(
            'spaCy model URL is not configured and no pre-installed model was found. '
            'Configure [guardrails] spacy_model_url in config.ini or install en_core_web_lg.'
        )

    # 3. Resolve target cache folder for effective_url
    dir_name = get_model_cache_dir_name(effective_url)
    target_dir = cache_root / dir_name
    sync_marker = target_dir / '.sync_complete'

    # Fast path: already cached and synced
    if target_dir.is_dir() and sync_marker.is_file():
        resolved = resolve_spacy_model_dir(target_dir)
        if (resolved / 'config.cfg').is_file():
            logger.debug('Using cached spaCy model at %s', resolved)
            return str(resolved)

    # Acquire thread lock and process-level file lock for multi-worker safety
    with _DOWNLOAD_LOCK:
        lock_file_path = cache_root / f'.{dir_name}.lock'
        lock_fd = None
        try:
            lock_fd = open(lock_file_path, 'w')
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        except (OSError, PermissionError):
            lock_fd = None

        try:
            # Re-check inside lock
            if target_dir.is_dir() and sync_marker.is_file():
                resolved = resolve_spacy_model_dir(target_dir)
                if (resolved / 'config.cfg').is_file():
                    logger.debug(
                        'spaCy model already cached by another worker at %s', resolved
                    )
                    return str(resolved)

            logger.info('Downloading spaCy model archive from %s...', effective_url)
            staging_dir = cache_root / f'.staging_{dir_name}_{Path(__file__).stem}'
            tmp_archive = cache_root / f'.tmp_{dir_name}.tar.gz'

            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if tmp_archive.exists():
                tmp_archive.unlink(missing_ok=True)

            staging_dir.mkdir(parents=True, exist_ok=True)

            try:
                download_file(effective_url, tmp_archive)
                extract_tar_archive(tmp_archive, staging_dir)

                if not (staging_dir / 'config.cfg').is_file():
                    found_configs = list(staging_dir.rglob('config.cfg'))
                    if not found_configs:
                        raise FileNotFoundError(
                            f"Model extraction completed, but config.cfg was not found in staging '{staging_dir}'."
                        )

                # Move staged directory to final target directory
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
                shutil.move(str(staging_dir), str(target_dir))

                resolved = resolve_spacy_model_dir(target_dir)
                sync_marker.write_text(f'source={effective_url}\n', encoding='utf-8')
                logger.info('spaCy model successfully cached at %s', resolved)
                return str(resolved)
            finally:
                if tmp_archive.exists():
                    tmp_archive.unlink(missing_ok=True)
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except OSError:
                    pass
                try:
                    lock_file_path.unlink(missing_ok=True)
                except OSError:
                    pass


def is_spacy_model_available(
    model_url: Optional[str] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    model_name: Optional[str] = None,
) -> bool:
    """Check whether a spaCy model can be resolved (via URL, cache, or pre-installed package)."""
    if model_url and model_url.strip():
        return True

    try:
        import spacy.util
    except ImportError:
        return False

    if model_name:
        try:
            if spacy.util.is_package(model_name):
                return True
        except Exception:
            pass
        candidate_name_path = Path(model_name)
        if (
            candidate_name_path.is_dir()
            and (resolve_spacy_model_dir(candidate_name_path) / 'config.cfg').is_file()
        ):
            return True

    cache_root = _resolve_cache_root(cache_dir)
    if cache_root.is_dir():
        if model_name:
            named_cache = cache_root / model_name
            if (
                named_cache.is_dir()
                and (named_cache / '.sync_complete').is_file()
                and (resolve_spacy_model_dir(named_cache) / 'config.cfg').is_file()
            ):
                return True
        try:
            for child in sorted(cache_root.iterdir()):
                if (
                    child.is_dir()
                    and (child / '.sync_complete').is_file()
                    and (resolve_spacy_model_dir(child) / 'config.cfg').is_file()
                ):
                    return True
        except OSError:
            pass

    for candidate in ('en_core_web_lg', 'en_core_web_sm', 'en_core_web_md'):
        try:
            if spacy.util.is_package(candidate):
                return True
        except Exception:
            pass

    return False
