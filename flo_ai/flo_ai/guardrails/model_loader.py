"""Utilities for resolving and lazy-downloading spaCy models from URLs or cloud storage."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from flo_ai.utils.logger import logger

_DOWNLOAD_LOCK = threading.Lock()


def resolve_spacy_model_dir(base_dir: Path) -> Path:
    """Find the directory containing config.cfg inside an extracted model directory."""
    if (base_dir / 'config.cfg').is_file():
        return base_dir
    # Check recursively for config.cfg (e.g. en_core_web_sm-3.8.0/en_core_web_sm/... inside archive)
    if base_dir.is_dir():
        matches = sorted(base_dir.rglob('config.cfg'), key=lambda p: len(p.parts))
        if matches:
            return matches[0].parent
    return base_dir


def get_model_cache_dir_name(url: str) -> str:
    """Derive a deterministic, safe directory name from a model URL or path."""
    parsed = urlparse(url)
    path_part = parsed.path.rstrip('/')
    filename = Path(path_part).name

    # Strip known archive extensions
    for ext in ('.tar.gz', '.tgz', '.tar', '.whl', '.zip'):
        if filename.lower().endswith(ext):
            filename = filename[: -len(ext)]
            break

    # Normalize wheel distribution tags if present (e.g. en_core_web_lg-3.8.0-py3-none-any)
    for tag in ('-py3-none-any', '-py2.py3-none-any', '-py38-none-any'):
        if tag in filename:
            filename = filename.replace(tag, '')

    clean_stem = re.sub(r'[^a-zA-Z0-9_\-]', '_', filename).strip('_')
    if not clean_stem:
        clean_stem = 'spacy_model'

    url_hash = hashlib.sha256(url.strip().encode('utf-8')).hexdigest()[:8]
    return f'{clean_stem}_{url_hash}'


def _download_stream_http(url: str, dest_path: Path) -> None:
    """Download a file from an HTTP/HTTPS URL streaming in chunks with configurable timeout."""
    timeout_s = float(os.getenv('GUARDRAILS_MODEL_DOWNLOAD_TIMEOUT_S', '300.0'))
    try:
        import httpx

        timeout = httpx.Timeout(connect=30.0, read=timeout_s, write=30.0, pool=30.0)
        with httpx.stream(
            'GET', url, follow_redirects=True, timeout=timeout
        ) as response:
            response.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout_s) as response, open(
            dest_path, 'wb'
        ) as f:
            shutil.copyfileobj(response, f, length=1024 * 1024)


def _download_s3(url: str, dest_path: Path) -> None:
    """Download an S3 object (s3://bucket/key) using boto3."""
    import boto3

    parsed = urlparse(url)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    if not bucket or not key:
        raise ValueError(f'Invalid S3 URI: {url!r}. Expected format: s3://bucket/key')

    s3_client = boto3.client('s3')
    s3_client.download_file(bucket, key, str(dest_path))


def _download_gcs(url: str, dest_path: Path) -> None:
    """Download a GCS object (gs://bucket/key) using google-cloud-storage."""
    from google.cloud import storage

    parsed = urlparse(url)
    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip('/')
    if not bucket_name or not blob_name:
        raise ValueError(f'Invalid GCS URI: {url!r}. Expected format: gs://bucket/key')

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(str(dest_path))


def download_file(url: str, dest_path: Path) -> None:
    """Download a file from a URL (http/https/s3/gs) or copy from local path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    url_clean = url.strip()
    scheme = urlparse(url_clean).scheme.lower()

    if scheme in ('http', 'https'):
        _download_stream_http(url_clean, dest_path)
    elif scheme == 's3':
        _download_s3(url_clean, dest_path)
    elif scheme == 'gs':
        _download_gcs(url_clean, dest_path)
    elif scheme == 'file' or not scheme or Path(url_clean).exists():
        local_src = Path(urlparse(url_clean).path if scheme == 'file' else url_clean)
        if not local_src.exists():
            raise FileNotFoundError(f'Local file not found: {local_src}')
        shutil.copy2(local_src, dest_path)
    else:
        raise ValueError(f'Unsupported URL scheme {scheme!r} in model URL: {url!r}')


def _is_safe_extraction_path(base_dir: Path, target_path: Path) -> bool:
    """Prevent directory traversal attacks during archive extraction."""
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def extract_archive(archive_path: Path, target_dir: Path) -> Path:
    """Safely extract .tar.gz, .tgz, .tar, or .zip archive to target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    name_lower = archive_path.name.lower()

    if name_lower.endswith(('.tar.gz', '.tgz', '.tar')):
        with tarfile.open(archive_path, 'r:*') as tar:
            if hasattr(tarfile, 'data_filter'):
                tar.extractall(path=target_dir, filter='data')
            else:
                for member in tar.getmembers():
                    dest = target_dir / member.name
                    if not _is_safe_extraction_path(target_dir, dest):
                        raise ValueError(
                            f'Path traversal detected in archive member: {member.name}'
                        )
                tar.extractall(path=target_dir)
    elif name_lower.endswith(('.zip', '.whl')):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            for member in zf.namelist():
                dest = target_dir / member
                if not _is_safe_extraction_path(target_dir, dest):
                    raise ValueError(
                        f'Path traversal detected in zip archive: {member}'
                    )
            zf.extractall(path=target_dir)
    else:
        raise ValueError(f'Unsupported archive format for file: {archive_path.name}')

    return resolve_spacy_model_dir(target_dir)


def _resolve_cache_root(cache_dir: Optional[Union[str, Path]]) -> Path:
    """Resolve and ensure accessibility of cache root directory with multi-tier fallback.

    Probes actual write permissions so that container-mounted read-only paths (e.g. root-owned volumes)
    gracefully fall back to user-writable directories without throwing PermissionError.
    """
    candidates: list[Path] = []
    if cache_dir is not None:
        candidates.append(Path(cache_dir))
    env_cache = os.getenv('GUARDRAILS_MODEL_CACHE_DIR')
    if env_cache:
        candidates.append(Path(env_cache))
    candidates.append(Path.home() / '.cache' / 'wavefront' / 'spacy')
    candidates.append(Path(tempfile.gettempdir()) / 'wavefront_spacy')

    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / f'.probe_write_{os.getpid()}'
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


def ensure_spacy_model(
    model_url: Optional[str] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    model_name: Optional[str] = None,
) -> str:
    """Resolve a spaCy model to a local directory or installed package name.

    1. Checks if model_url is an installed package or local directory with config.cfg.
    2. Checks if model_name is an installed package or local directory.
    3. If model_url is provided (or GUARDRAILS_SPACY_MODEL_URL is set), downloads and caches it:
       - Uses thread lock and process-level file lock (fcntl.flock) for multi-worker safety.
       - Validates archive members to prevent path traversal (Zip Slip).
       - Extracts into atomic staging directory before publishing with .sync_complete.
    4. If neither URL nor installed package is available, checks pre-installed models or cache fallback.

    Returns:
        String path to the local model folder, or package name if installed.
    """
    import spacy.util

    cache_root = _resolve_cache_root(cache_dir)
    effective_url = (
        model_url or os.getenv('GUARDRAILS_SPACY_MODEL_URL') or ''
    ).strip() or None

    # Check if effective_url is actually an installed package name (e.g. "en_core_web_sm")
    if effective_url and spacy.util.is_package(effective_url):
        logger.debug("spaCy model '%s' is an installed Python package", effective_url)
        return effective_url

    # Check if effective_url is a direct local directory on disk
    if effective_url:
        candidate_path = Path(effective_url)
        if (
            candidate_path.is_dir()
            and (resolve_spacy_model_dir(candidate_path) / 'config.cfg').is_file()
        ):
            resolved = resolve_spacy_model_dir(candidate_path)
            logger.debug("Using direct local directory for spaCy model '%s'", resolved)
            return str(resolved)

    # Check if model_name was explicitly passed and is an installed package, directory, or cached
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
                'and GUARDRAILS_SPACY_MODEL_URL is not set.'
            )

    # If no URL is provided, check cache root and installed packages before failing
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

        # Fallback for dev environments if explicitly permitted
        if os.getenv('ALLOW_SPACY_INTERNET_DOWNLOAD', 'false').lower() in ('1', 'true'):
            fallback_target = model_name or 'en_core_web_sm'
            logger.info("Attempting spacy.cli.download for '%s'...", fallback_target)
            import spacy.cli

            spacy.cli.download(fallback_target)
            return fallback_target

        raise RuntimeError(
            'spaCy model URL is not configured and no pre-installed model was found. '
            'Set GUARDRAILS_SPACY_MODEL_URL to point to a model archive (e.g. https://... or s3://...).'
        )

    # Resolve target folder for effective_url
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
            import fcntl

            lock_fd = open(lock_file_path, 'w')
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        except (OSError, ImportError, PermissionError):
            lock_fd = None

        try:
            # Re-check inside process lock: another worker may have finished while we waited
            if target_dir.is_dir() and sync_marker.is_file():
                resolved = resolve_spacy_model_dir(target_dir)
                if (resolved / 'config.cfg').is_file():
                    logger.debug(
                        'spaCy model already cached by another worker at %s', resolved
                    )
                    return str(resolved)

            logger.info('Downloading spaCy model from %s...', effective_url)

            # Determine archive extension
            url_path = urlparse(effective_url).path.lower()
            if url_path.endswith(('.tar.gz', '.tgz', '.tar')):
                ext = '.tar.gz'
            elif url_path.endswith('.whl'):
                ext = '.whl'
            elif url_path.endswith('.zip'):
                ext = '.zip'
            else:
                ext = '.tar.gz'

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_archive = Path(tmp.name)

            # Stage extraction in a unique temporary directory to guarantee atomic publishing
            staging_dir = cache_root / f'.tmp_{dir_name}_{os.getpid()}'
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

            try:
                download_file(effective_url, tmp_archive)
                logger.info(
                    'Extracting model archive (%d bytes) to staging...',
                    tmp_archive.stat().st_size,
                )
                extract_archive(tmp_archive, staging_dir)

                resolved_staging = resolve_spacy_model_dir(staging_dir)
                if not (resolved_staging / 'config.cfg').is_file():
                    raise RuntimeError(
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
                    import fcntl

                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except OSError:
                    pass
                try:
                    lock_file_path.unlink(missing_ok=True)
                except OSError:
                    pass
