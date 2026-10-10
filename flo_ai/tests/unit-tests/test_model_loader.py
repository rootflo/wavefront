"""Unit tests for flo_ai.guardrails.model_loader."""

import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from flo_ai.guardrails.model_loader import (
    ensure_spacy_model,
    get_model_cache_dir_name,
    resolve_spacy_model_dir,
)


def _create_mock_model_tar(
    tar_path: Path, model_name: str, nested: bool = True
) -> None:
    """Helper to create a valid-looking spaCy model .tar.gz archive."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / model_name
        if nested:
            inner = src / f'{model_name}-3.8.0'
            inner.mkdir(parents=True)
            (inner / 'config.cfg').write_text("[nlp]\nlang = 'en'\n", encoding='utf-8')
        else:
            src.mkdir(parents=True)
            (src / 'config.cfg').write_text("[nlp]\nlang = 'en'\n", encoding='utf-8')

        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(src, arcname=model_name)


def test_resolve_spacy_model_dir_direct():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'config.cfg').write_text('[nlp]\n', encoding='utf-8')
        assert resolve_spacy_model_dir(p) == p


def test_resolve_spacy_model_dir_nested():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        nested = base / 'inner_model'
        nested.mkdir()
        (nested / 'config.cfg').write_text('[nlp]\n', encoding='utf-8')
        assert resolve_spacy_model_dir(base) == nested


def test_installed_package_hit():
    with patch('spacy.util.is_package', return_value=True):
        res = ensure_spacy_model('en_core_web_sm')
        assert res == 'en_core_web_sm'


def test_direct_local_dir_hit():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'config.cfg').write_text('[nlp]\n', encoding='utf-8')
        res = ensure_spacy_model(str(p))
        assert res == str(p)


def test_cache_hit():
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        url = 'https://models.example.com/my_model.tar.gz'
        dir_name = get_model_cache_dir_name(url)
        target = cache_dir / dir_name
        target.mkdir()
        (target / '.sync_complete').write_text('source=test\n', encoding='utf-8')
        (target / 'config.cfg').write_text('[nlp]\n', encoding='utf-8')

        with patch('spacy.util.is_package', return_value=False):
            res = ensure_spacy_model(model_url=url, cache_dir=cache_dir)
            assert res == str(target)


def test_local_archive_download_and_extract():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / 'model.tar.gz'
        _create_mock_model_tar(archive, 'test_model', nested=True)

        cache_dir = tmp_path / 'cache'

        with patch('spacy.util.is_package', return_value=False):
            resolved = ensure_spacy_model(
                model_url=str(archive),
                cache_dir=cache_dir,
            )
            resolved_path = Path(resolved)
            assert resolved_path.is_dir()
            assert (resolved_path / 'config.cfg').is_file()
            dir_name = get_model_cache_dir_name(str(archive))
            assert (cache_dir / dir_name / '.sync_complete').is_file()


def test_mock_http_download_and_extract():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / 'dummy.tar.gz'
        _create_mock_model_tar(archive, 'web_model', nested=False)

        cache_dir = tmp_path / 'cache'

        def _mock_download(url, dest):
            import shutil

            shutil.copy2(archive, dest)

        with patch('spacy.util.is_package', return_value=False), patch(
            'flo_ai.guardrails.model_loader._download_stream_http',
            side_effect=_mock_download,
        ):
            resolved = ensure_spacy_model(
                model_url='https://models.example.com/web_model.tar.gz',
                cache_dir=cache_dir,
            )
            resolved_path = Path(resolved)
            assert resolved_path.is_dir()
            assert (resolved_path / 'config.cfg').is_file()


def test_missing_url_and_not_installed_raises():
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        with patch.dict('os.environ', {}, clear=True), patch(
            'spacy.util.is_package', return_value=False
        ):
            with pytest.raises(RuntimeError, match='GUARDRAILS_SPACY_MODEL_URL'):
                ensure_spacy_model(model_url=None, cache_dir=cache_dir)


def test_permission_error_cache_dir_fallback():
    with tempfile.TemporaryDirectory():
        unwritable_dir = Path('/nonexistent_root_dir_for_test/models/spacy')
        with patch.dict('os.environ', {}, clear=True), patch(
            'spacy.util.is_package', return_value=False
        ):
            with pytest.raises(RuntimeError, match='GUARDRAILS_SPACY_MODEL_URL'):
                ensure_spacy_model(model_name='missing_model', cache_dir=unwritable_dir)


def test_whl_download_and_extract():
    import zipfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        whl_path = tmp_path / 'model-3.8.0-py3-none-any.whl'
        with zipfile.ZipFile(whl_path, 'w') as zf:
            zf.writestr('model/config.cfg', "[nlp]\nlang = 'en'\n")

        cache_dir = tmp_path / 'cache'

        def _mock_download(url, dest):
            import shutil

            shutil.copy2(whl_path, dest)

        with patch('spacy.util.is_package', return_value=False), patch(
            'flo_ai.guardrails.model_loader._download_stream_http',
            side_effect=_mock_download,
        ):
            resolved = ensure_spacy_model(
                model_url='https://models.example.com/model-3.8.0-py3-none-any.whl',
                cache_dir=cache_dir,
            )
            resolved_path = Path(resolved)
            assert resolved_path.is_dir()
            assert (resolved_path / 'config.cfg').is_file()
