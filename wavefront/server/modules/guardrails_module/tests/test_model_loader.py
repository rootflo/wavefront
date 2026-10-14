"""Unit tests for guardrails_module.services.model_loader."""

import io
from pathlib import Path
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from guardrails_module.services.model_loader import (
    _is_safe_extraction_path,
    cli_main,
    download_file,
    ensure_spacy_model,
    extract_tar_archive,
    get_model_cache_dir_name,
    is_spacy_model_available,
    resolve_spacy_model_dir,
)


def _create_dummy_tar_gz(dest: Path, model_subdir: str = 'en_core_web_sm') -> Path:
    """Helper to build an in-memory tar.gz model archive on disk."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, 'w:gz') as tar:
        config_content = b'[nlp]\nlang = "en"\n'
        tarinfo = tarfile.TarInfo(name=f'{model_subdir}/config.cfg')
        tarinfo.size = len(config_content)
        tar.addfile(tarinfo, io.BytesIO(config_content))
    return dest


class TestSafeExtraction:
    def test_safe_path(self, tmp_path):
        base = tmp_path / 'base'
        target = base / 'sub' / 'file.txt'
        assert _is_safe_extraction_path(base, target) is True

    def test_traversal_path(self, tmp_path):
        base = tmp_path / 'base'
        target = tmp_path / 'outside' / 'file.txt'
        assert _is_safe_extraction_path(base, target) is False


class TestResolveSpacyModelDir:
    def test_direct_config(self, tmp_path):
        (tmp_path / 'config.cfg').write_text('lang = en', encoding='utf-8')
        assert resolve_spacy_model_dir(tmp_path) == tmp_path

    def test_nested_config(self, tmp_path):
        sub = tmp_path / 'pkg' / 'model-1.0.0'
        sub.mkdir(parents=True)
        (sub / 'config.cfg').write_text('lang = en', encoding='utf-8')
        assert resolve_spacy_model_dir(tmp_path) == sub

    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match='config.cfg not found'):
            resolve_spacy_model_dir(tmp_path)


class TestExtractArchive:
    def test_extract_tar_gz(self, tmp_path):
        archive = _create_dummy_tar_gz(tmp_path / 'model.tar.gz', 'test_model')
        target = tmp_path / 'extracted'
        resolved = extract_tar_archive(archive, target)
        assert (resolved / 'config.cfg').is_file()
        assert resolved.name == 'test_model'

    def test_fallback_rejects_symlink(self, tmp_path, monkeypatch):
        archive_path = tmp_path / 'symlink.tar.gz'
        with tarfile.open(archive_path, 'w:gz') as tar:
            link_info = tarfile.TarInfo('test_model/link')
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = '/etc/passwd'
            tar.addfile(link_info)

        target = tmp_path / 'extracted'
        monkeypatch.delattr(tarfile, 'data_filter', raising=False)
        with pytest.raises(ValueError, match='Archive link detected in member'):
            extract_tar_archive(archive_path, target)

    def test_fallback_rejects_hardlink(self, tmp_path, monkeypatch):
        archive_path = tmp_path / 'hardlink.tar.gz'
        with tarfile.open(archive_path, 'w:gz') as tar:
            link_info = tarfile.TarInfo('test_model/hardlink')
            link_info.type = tarfile.LNKTYPE
            link_info.linkname = 'some_target'
            tar.addfile(link_info)

        target = tmp_path / 'extracted'
        monkeypatch.delattr(tarfile, 'data_filter', raising=False)
        with pytest.raises(ValueError, match='Archive link detected in member'):
            extract_tar_archive(archive_path, target)

    def test_fallback_rejects_path_traversal(self, tmp_path, monkeypatch):
        archive_path = tmp_path / 'traversal.tar.gz'
        with tarfile.open(archive_path, 'w:gz') as tar:
            content = b'escape'
            tarinfo = tarfile.TarInfo('../outside.txt')
            tarinfo.size = len(content)
            tar.addfile(tarinfo, io.BytesIO(content))

        target = tmp_path / 'extracted'
        monkeypatch.delattr(tarfile, 'data_filter', raising=False)
        with pytest.raises(
            ValueError, match='Path traversal detected in archive member'
        ):
            extract_tar_archive(archive_path, target)


class TestGetModelCacheDirName:
    def test_clean_name(self):
        url = 'https://example.com/en_core_web_sm-3.8.0.tar.gz'
        name = get_model_cache_dir_name(url)
        assert 'en_core_web_sm-3_8_0' in name

    def test_deterministic(self):
        url = 's3://my-bucket/model.tar.gz'
        assert get_model_cache_dir_name(url) == get_model_cache_dir_name(url)


class TestDownloadFile:
    def test_download_local_file(self, tmp_path):
        src = tmp_path / 'src.txt'
        src.write_text('hello world', encoding='utf-8')
        dest = tmp_path / 'dest.txt'
        download_file(str(src), dest)
        assert dest.read_text(encoding='utf-8') == 'hello world'

    def test_download_http(self, tmp_path):
        dest = tmp_path / 'dest.tar.gz'
        with patch(
            'guardrails_module.services.model_loader._download_stream_http'
        ) as mock_http:
            download_file('https://example.com/model.tar.gz', dest)
            mock_http.assert_called_once_with('https://example.com/model.tar.gz', dest)

    def test_download_stream_http_with_progress(self, tmp_path):
        from guardrails_module.services.model_loader import _download_stream_http

        dest = tmp_path / 'downloaded.tar.gz'
        fake_content = b'model data chunk 1' * 1000
        mock_response = MagicMock()
        mock_response.headers = {'Content-Length': str(len(fake_content))}
        mock_response.read.side_effect = [fake_content[:5000], fake_content[5000:], b'']
        mock_response.__enter__.return_value = mock_response

        with patch('urllib.request.urlopen', return_value=mock_response):
            _download_stream_http('https://example.com/model.tar.gz', dest)

        assert dest.exists()
        assert dest.read_bytes() == fake_content

    def test_download_s3_via_flo_cloud(self, tmp_path):
        dest = tmp_path / 'dest.tar.gz'
        mock_storage = MagicMock()
        mock_storage.get_bucket_key.return_value = ('my-bucket', 'model.tar.gz')
        with patch(
            'flo_cloud.cloud_storage.CloudStorageManager', return_value=mock_storage
        ):
            download_file('s3://my-bucket/model.tar.gz', dest)
            mock_storage.handler.s3_client.download_file.assert_called_once_with(
                'my-bucket', 'model.tar.gz', str(dest)
            )

    def test_download_gcs_via_flo_cloud(self, tmp_path):
        dest = tmp_path / 'dest.tar.gz'
        mock_storage = MagicMock()
        mock_storage.get_bucket_key.return_value = ('my-gcs-bucket', 'model.tar.gz')
        with patch(
            'flo_cloud.cloud_storage.CloudStorageManager', return_value=mock_storage
        ):
            download_file('gs://my-gcs-bucket/model.tar.gz', dest)
            mock_storage.handler.client.bucket().blob().download_to_filename.assert_called_once_with(
                str(dest)
            )

    def test_download_unsupported_scheme(self, tmp_path):
        with pytest.raises(ValueError, match='Unsupported URL scheme'):
            download_file('ftp://example.com/model.tar.gz', tmp_path / 'dest.tar.gz')


class TestEnsureSpacyModel:
    def test_cached_model_fast_path(self, tmp_path):
        cache_dir = tmp_path / 'cache'
        model_url = 'https://example.com/model.tar.gz'
        dir_name = get_model_cache_dir_name(model_url)
        target = cache_dir / dir_name
        target.mkdir(parents=True)
        (target / '.sync_complete').write_text('source=test', encoding='utf-8')
        (target / 'config.cfg').write_text('lang=en', encoding='utf-8')

        resolved = ensure_spacy_model(model_url=model_url, cache_dir=cache_dir)
        assert resolved == str(target)

    def test_download_and_extract_flow(self, tmp_path):
        cache_dir = tmp_path / 'cache'
        archive_src = _create_dummy_tar_gz(tmp_path / 'src_model.tar.gz')

        with patch(
            'guardrails_module.services.model_loader.download_file'
        ) as mock_download:

            def side_effect(url, dest):
                import shutil

                shutil.copy2(archive_src, dest)

            mock_download.side_effect = side_effect

            resolved = ensure_spacy_model(
                model_url='https://example.com/src_model.tar.gz',
                cache_dir=cache_dir,
            )
            assert Path(resolved).is_dir()
            assert (Path(resolved) / 'config.cfg').is_file()
            # Verify marker was written
            parent_target = (
                Path(resolved).parent
                if Path(resolved).name == 'en_core_web_sm'
                else Path(resolved)
            )
            assert (parent_target / '.sync_complete').is_file()

    def test_missing_model_and_url_raises(self, tmp_path):
        with patch('spacy.util.is_package', return_value=False):
            with pytest.raises(RuntimeError, match='spaCy model URL is not configured'):
                ensure_spacy_model(model_url=None, cache_dir=tmp_path / 'empty')


class TestIsSpacyModelAvailable:
    def test_available_with_url(self):
        assert (
            is_spacy_model_available(model_url='https://example.com/model.tar.gz')
            is True
        )

    def test_available_with_installed_package(self):
        with patch(
            'spacy.util.is_package', side_effect=lambda name: name == 'en_core_web_lg'
        ):
            assert is_spacy_model_available(model_url=None) is True

    def test_available_with_named_cached_model(self, tmp_path):
        cache_dir = tmp_path / 'cache'
        model_dir = cache_dir / 'cached_model'
        model_dir.mkdir(parents=True)
        (model_dir / '.sync_complete').write_text('source=test', encoding='utf-8')
        (model_dir / 'config.cfg').write_text('lang=en', encoding='utf-8')

        with patch('spacy.util.is_package', return_value=False):
            assert (
                is_spacy_model_available(
                    model_url=None, model_name='cached_model', cache_dir=cache_dir
                )
                is True
            )

    def test_unavailable_when_url_unset_even_with_cached_models(self, tmp_path):
        cache_dir = tmp_path / 'cache'
        model_dir = cache_dir / 'old_model'
        model_dir.mkdir(parents=True)
        (model_dir / '.sync_complete').write_text('source=test', encoding='utf-8')
        (model_dir / 'config.cfg').write_text('lang=en', encoding='utf-8')

        with patch('spacy.util.is_package', return_value=False):
            assert (
                is_spacy_model_available(model_url=None, cache_dir=cache_dir) is False
            )

    def test_unavailable_when_no_source(self, tmp_path):
        with patch('spacy.util.is_package', return_value=False):
            assert (
                is_spacy_model_available(model_url=None, cache_dir=tmp_path / 'empty')
                is False
            )


class TestCliMain:
    """Tests for the CLI entrypoint."""

    def test_cli_main_success_with_args(self, tmp_path):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        ret = cli_main(['--url', archive.as_uri(), '--cache-dir', str(cache_dir)])
        assert ret == 0

        # Assert model is extracted and marked complete
        assert any(
            (p / '.sync_complete').is_file() for p in cache_dir.iterdir() if p.is_dir()
        )

    def test_cli_main_fallback_to_env(self, tmp_path, monkeypatch):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        monkeypatch.setenv('GUARDRAILS_SPACY_MODEL_URL', archive.as_uri())
        monkeypatch.setenv('GUARDRAILS_MODEL_CACHE_DIR', str(cache_dir))

        ret = cli_main([])
        assert ret == 0

    def test_cli_main_no_url_error(self, monkeypatch):
        monkeypatch.delenv('GUARDRAILS_SPACY_MODEL_URL', raising=False)
        ret = cli_main([])
        assert ret == 1

    def test_cli_main_check_only_available(self, tmp_path):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'
        cli_main(['--url', archive.as_uri(), '--cache-dir', str(cache_dir)])

        ret = cli_main(
            ['--url', archive.as_uri(), '--cache-dir', str(cache_dir), '--check-only']
        )
        assert ret == 0

    def test_cli_main_check_only_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.delenv('GUARDRAILS_SPACY_MODEL_URL', raising=False)
        with patch('spacy.util.is_package', return_value=False):
            ret = cli_main(['--cache-dir', str(tmp_path), '--check-only'])
            assert ret == 1

    def test_cli_main_download_failure(self):
        with patch(
            'guardrails_module.services.model_loader.ensure_spacy_model',
            side_effect=RuntimeError('Network failure'),
        ):
            ret = cli_main(['--url', 'https://example.com/fail.tar.gz'])
            assert ret == 1

    def test_cli_main_skipped_when_disabled(self, tmp_path):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        ret = cli_main(
            [
                '--enabled',
                'false',
                '--url',
                archive.as_uri(),
                '--cache-dir',
                str(cache_dir),
            ]
        )
        assert ret == 0
        # Assert no model was extracted
        assert not cache_dir.exists() or not any(cache_dir.iterdir())

    def test_cli_main_skipped_when_disabled_via_env(self, tmp_path, monkeypatch):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        monkeypatch.setenv('GUARDRAILS_ENABLED', 'false')
        monkeypatch.setenv('GUARDRAILS_SPACY_MODEL_URL', archive.as_uri())
        monkeypatch.setenv('GUARDRAILS_MODEL_CACHE_DIR', str(cache_dir))

        ret = cli_main([])
        assert ret == 0
        assert not cache_dir.exists() or not any(cache_dir.iterdir())

    def test_cli_main_force_overrides_disabled(self, tmp_path, monkeypatch):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        monkeypatch.setenv('GUARDRAILS_ENABLED', 'false')
        monkeypatch.setenv('GUARDRAILS_SPACY_MODEL_URL', archive.as_uri())
        monkeypatch.setenv('GUARDRAILS_MODEL_CACHE_DIR', str(cache_dir))

        ret = cli_main(['--force'])
        assert ret == 0
        assert any(
            (p / '.sync_complete').is_file() for p in cache_dir.iterdir() if p.is_dir()
        )

    def test_cli_main_enabled_true_no_url_warns_and_succeeds(self, monkeypatch):
        monkeypatch.setenv('GUARDRAILS_ENABLED', 'true')
        monkeypatch.delenv('GUARDRAILS_SPACY_MODEL_URL', raising=False)
        ret = cli_main([])
        assert ret == 0

    def test_load_guardrails_model_config_from_ini(self, tmp_path):
        from guardrails_module.services.model_loader import load_guardrails_model_config

        ini_file = tmp_path / 'test_config.ini'
        ini_file.write_text(
            '[guardrails]\n'
            'enabled = true\n'
            'spacy_model_url = https://example.com/spacy.tar.gz\n'
            'model_cache_dir = /tmp/spacy_cache\n'
            '\n'
            '[env_config]\n'
            'log_level = DEBUG\n'
        )

        cfg = load_guardrails_model_config(ini_file)
        assert cfg.enabled is True
        assert cfg.model_url == 'https://example.com/spacy.tar.gz'
        assert cfg.model_cache_dir == '/tmp/spacy_cache'
        assert cfg.log_level == 'DEBUG'

    def test_cli_main_with_config_flag(self, tmp_path):
        archive = _create_dummy_tar_gz(tmp_path / 'archive' / 'model.tar.gz')
        cache_dir = tmp_path / 'cache'

        ini_file = tmp_path / 'custom_config.ini'
        ini_file.write_text(
            '[guardrails]\n'
            'enabled = true\n'
            f'spacy_model_url = {archive.as_uri()}\n'
            f'model_cache_dir = {cache_dir}\n'
        )

        ret = cli_main(['--config', str(ini_file)])
        assert ret == 0
        assert any(
            (p / '.sync_complete').is_file() for p in cache_dir.iterdir() if p.is_dir()
        )
