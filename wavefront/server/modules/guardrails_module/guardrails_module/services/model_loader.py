"""Model loader for Guardrails spaCy models in Wavefront server.

Downloads, verifies, and extracts spaCy model archives (.tar.gz) from cloud storage
(S3, GCS, Azure Blob via flo_cloud) or HTTP/HTTPS into a local directory with atomic
disk-caching and multi-worker process locking.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import hashlib
import logging
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import threading
import time
from typing import Optional, Union
from urllib.parse import urlparse
import urllib.request

from common_module.config_loader import is_truthy
from common_module.log.logger import configure_logging
from dependency_injector import providers

logger = logging.getLogger('guardrails_model_init')

_DOWNLOAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class GuardrailsModelConfig:
    enabled: bool = False
    model_url: Optional[str] = None
    model_cache_dir: Optional[str] = None
    log_level: str = 'INFO'


def find_config_ini(explicit_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Find the Wavefront config.ini file across standard container and repository locations."""
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f'Config file not found at: {explicit_path}')

    candidates = [
        Path('/app/apps/floware/floware/config.ini'),
        Path(__file__).resolve().parents[4]
        / 'apps'
        / 'floware'
        / 'floware'
        / 'config.ini',
        Path.cwd() / 'apps' / 'floware' / 'floware' / 'config.ini',
        Path.cwd() / 'floware' / 'config.ini',
        Path.cwd() / 'config.ini',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_guardrails_model_config(
    config_path: Optional[Union[str, Path]] = None,
) -> GuardrailsModelConfig:
    """Load guardrails model settings from config.ini via dependency_injector Configuration."""
    resolved_ini = find_config_ini(config_path)
    if not resolved_ini:
        return GuardrailsModelConfig()

    cfg = providers.Configuration()
    cfg.from_ini(str(resolved_ini), required=True, envs_required=False)

    raw_enabled = (
        cfg.guardrails.enabled() if hasattr(cfg.guardrails, 'enabled') else None
    )
    enabled = is_truthy(raw_enabled)

    raw_url = (
        cfg.guardrails.spacy_model_url()
        if hasattr(cfg.guardrails, 'spacy_model_url')
        else None
    )
    url = str(raw_url).strip() if raw_url and str(raw_url).strip() else None

    raw_cache_dir = (
        cfg.guardrails.model_cache_dir()
        if hasattr(cfg.guardrails, 'model_cache_dir')
        else None
    )
    cache_dir = (
        str(raw_cache_dir).strip()
        if raw_cache_dir and str(raw_cache_dir).strip()
        else None
    )

    raw_log_level = (
        cfg.env_config.log_level() if hasattr(cfg.env_config, 'log_level') else None
    )
    log_level = (
        str(raw_log_level).strip().upper()
        if raw_log_level and str(raw_log_level).strip()
        else 'INFO'
    )

    return GuardrailsModelConfig(
        enabled=enabled,
        model_url=url,
        model_cache_dir=cache_dir,
        log_level=log_level,
    )


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
    logger.info(
        "Extracting spaCy model archive '%s' to '%s'...", archive_path.name, target_dir
    )
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

    resolved = resolve_spacy_model_dir(target_dir)
    logger.info("Extraction complete. Model configuration located at '%s'.", resolved)
    return resolved


def _resolve_cache_root(cache_dir: Optional[Union[str, Path]]) -> Path:
    """Resolve and verify cache root directory with multi-tier fallback."""
    if cache_dir is None:
        cfg = load_guardrails_model_config()
        cache_dir = cfg.model_cache_dir

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
    """Stream download over HTTP/HTTPS in 1MB chunks with progress logging."""
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Wavefront-ModelLoader/1.0'}
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as response, open(
        dest_path, 'wb'
    ) as f:
        total_header = (
            getattr(response, 'headers', {}).get('Content-Length')
            if hasattr(response, 'headers')
            else None
        )
        total_bytes = (
            int(total_header) if total_header and str(total_header).isdigit() else 0
        )

        if total_bytes > 0:
            logger.info(
                "Starting download from '%s' (total size: %.2f MB)...",
                url,
                total_bytes / (1024 * 1024),
            )
        else:
            logger.info("Starting download from '%s'...", url)

        chunk_size = 1024 * 1024  # 1 MB chunks
        downloaded = 0
        last_logged_bytes = 0
        last_logged_time = time.time()

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()

            # Log every 20 MB or at least every 5 seconds
            if (downloaded - last_logged_bytes >= 20 * 1024 * 1024) or (
                now - last_logged_time >= 5.0
            ):
                last_logged_bytes = downloaded
                last_logged_time = now
                if total_bytes > 0:
                    pct = (downloaded / total_bytes) * 100
                    logger.info(
                        'Download progress: %.1f MB / %.1f MB (%.1f%%)',
                        downloaded / (1024 * 1024),
                        total_bytes / (1024 * 1024),
                        pct,
                    )
                else:
                    logger.info(
                        'Download progress: %.1f MB downloaded...',
                        downloaded / (1024 * 1024),
                    )

        logger.info(
            'Download completed: %.2f MB received and written to %s.',
            downloaded / (1024 * 1024),
            dest_path.name,
        )


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

        logger.info("Starting cloud download of spaCy model from '%s'...", url_clean)

        if scheme == 's3':
            storage.handler.s3_client.download_file(bucket, key, str(dest_path))
            logger.info('S3 download completed: %s', dest_path)
        elif scheme == 'gs':
            storage.handler.client.bucket(bucket).blob(key).download_to_filename(
                str(dest_path)
            )
            logger.info('GCS download completed: %s', dest_path)
        elif scheme == 'azure':
            blob_client = storage.handler.client.get_blob_client(
                container=bucket, blob=key
            )
            with open(dest_path, 'wb') as f:
                blob_client.download_blob().readinto(f)
            logger.info('Azure Blob download completed: %s', dest_path)
    elif scheme in ('http', 'https'):
        _download_stream_http(url_clean, dest_path)
    elif scheme == 'file' or not scheme or Path(url_clean).exists():
        local_src = Path(urlparse(url_clean).path if scheme == 'file' else url_clean)
        if not local_src.exists():
            raise FileNotFoundError(f'Local file not found: {local_src}')
        logger.info("Copying local spaCy model archive from '%s'...", local_src)
        shutil.copy2(local_src, dest_path)
        logger.info('Local copy completed: %s', dest_path)
    else:
        raise ValueError(f'Unsupported URL scheme {scheme!r} in model URL: {url!r}')


def ensure_spacy_model(
    model_url: Optional[str] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    model_name: Optional[str] = None,
) -> str:
    """Resolve or download spaCy model archive (.tar.gz) to local cache and return directory path."""
    import spacy.util

    if model_url is None or cache_dir is None:
        cfg = load_guardrails_model_config()
        if model_url is None:
            model_url = cfg.model_url
        if cache_dir is None:
            cache_dir = cfg.model_cache_dir

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
        if cache_dir:
            named_cache = Path(cache_dir) / model_name
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

    # 2. If no URL is provided, check installed packages in Python environment
    if not effective_url:
        for candidate in ('en_core_web_lg', 'en_core_web_sm', 'en_core_web_md'):
            if spacy.util.is_package(candidate):
                logger.debug("Found pre-installed fallback spaCy model '%s'", candidate)
                return candidate

        raise RuntimeError(
            'spaCy model URL is not configured and no pre-installed model was found. '
            'Configure [guardrails] spacy_model_url in config.ini or install en_core_web_lg.'
        )

    # 3. Fast path: check if model is ALREADY cached in cache_dir without needing write permission
    dir_name = get_model_cache_dir_name(effective_url)
    if cache_dir:
        candidate_target = Path(cache_dir) / dir_name
        sync_marker = candidate_target / '.sync_complete'
        if candidate_target.is_dir() and sync_marker.is_file():
            resolved = resolve_spacy_model_dir(candidate_target)
            if (resolved / 'config.cfg').is_file():
                logger.debug('Using cached spaCy model at %s', resolved)
                return str(resolved)

    # 4. Model not yet cached: resolve a writable cache root to download into
    cache_root = _resolve_cache_root(cache_dir)
    target_dir = cache_root / dir_name
    sync_marker = target_dir / '.sync_complete'

    # Check fast path in resolved cache root
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
    if model_url is None or cache_dir is None:
        cfg = load_guardrails_model_config()
        if model_url is None:
            model_url = cfg.model_url
        if cache_dir is None:
            cache_dir = cfg.model_cache_dir

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

    if model_name:
        if cache_dir and Path(cache_dir).is_dir():
            named_cache = Path(cache_dir) / model_name
            if (
                named_cache.is_dir()
                and (named_cache / '.sync_complete').is_file()
                and (resolve_spacy_model_dir(named_cache) / 'config.cfg').is_file()
            ):
                return True
        cache_root = _resolve_cache_root(cache_dir)
        if cache_root.is_dir():
            named_cache = cache_root / model_name
            if (
                named_cache.is_dir()
                and (named_cache / '.sync_complete').is_file()
                and (resolve_spacy_model_dir(named_cache) / 'config.cfg').is_file()
            ):
                return True

    for candidate in ('en_core_web_lg', 'en_core_web_sm', 'en_core_web_md'):
        try:
            if spacy.util.is_package(candidate):
                return True
        except Exception:
            pass

    return False


def cli_main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint for pre-populating or checking the guardrails spaCy model cache."""
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description='Pre-download and cache spaCy model archives for Floware guardrails.',
    )
    parser.add_argument(
        '--config',
        default=None,
        help='Optional path to config.ini file.',
    )
    parser.add_argument(
        '--url',
        default=None,
        help='Source URL or cloud path (s3://, gs://, azure://, https://, file://). Defaults to [guardrails] spacy_model_url in config.ini.',
    )
    parser.add_argument(
        '--cache-dir',
        default=None,
        help='Target cache directory. Defaults to [guardrails] model_cache_dir in config.ini.',
    )
    parser.add_argument(
        '--model-name',
        default=None,
        help='Optional explicit model name or directory alias.',
    )
    parser.add_argument(
        '--enabled',
        default=None,
        help="Master guardrails enabled toggle ('true'/'false'). Defaults to [guardrails] enabled in config.ini.",
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force download even if guardrails is disabled in config.',
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Check whether the model is already available without downloading.',
    )

    args = parser.parse_args(argv)

    # 1. Load config from config.ini
    cfg = load_guardrails_model_config(args.config)

    # 2. Configure logging with dedicated service name 'guardrails_model_init'
    log_level = cfg.log_level
    try:
        configure_logging(app_name='guardrails_model_init', log_level=log_level)
    except Exception:
        import logging

        logging.basicConfig(
            level=log_level, format='%(asctime)s | %(levelname)-8s | %(message)s'
        )

    logger.info('Guardrails spaCy model init service starting...')

    # 3. Resolve effective settings (CLI arguments take precedence over config.ini)
    if args.url is not None:
        effective_url = args.url
        effective_enabled = args.enabled if args.enabled is not None else True
    else:
        effective_url = cfg.model_url
        effective_enabled = args.enabled if args.enabled is not None else cfg.enabled
    effective_cache_dir = (
        args.cache_dir if args.cache_dir is not None else cfg.model_cache_dir
    )

    logger.info(
        'Model loader configuration: enabled=%s, url=%s, cache_dir=%s',
        effective_enabled,
        effective_url or '(none)',
        effective_cache_dir or '(default)',
    )

    if args.check_only:
        available = is_spacy_model_available(
            model_url=effective_url,
            cache_dir=effective_cache_dir,
            model_name=args.model_name,
        )
        if available:
            logger.info('spaCy model is available.')
            return 0
        logger.warning('spaCy model is NOT available.')
        return 1

    if not effective_url or not effective_url.strip():
        if is_truthy(effective_enabled):
            logger.warning(
                'Guardrails is enabled, but no model URL was configured in [guardrails] spacy_model_url or passed via --url. Skipping model download.'
            )
            return 0
        logger.error(
            'No model URL provided. Specify --url or configure [guardrails] spacy_model_url in config.ini.',
            exc_info=False,
        )
        return 1

    # An effective URL was provided; check if guardrails is explicitly disabled (unless --force is passed)
    if not args.force and not is_truthy(effective_enabled):
        logger.info(
            'Guardrails is not enabled (enabled=%r). Skipping spaCy model download.',
            effective_enabled,
        )
        return 0

    try:
        resolved = ensure_spacy_model(
            model_url=effective_url,
            cache_dir=effective_cache_dir,
            model_name=args.model_name,
        )
        logger.info('spaCy model ready at: %s', resolved)
        return 0
    except Exception as exc:
        logger.error('Failed to acquire spaCy model: %s', exc)
        return 1


if __name__ == '__main__':
    sys.exit(cli_main())
