"""Unit tests for RecaptchaService.verify branches."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from user_management_module.services.recaptcha_service import RecaptchaService


def _enabled_service(**overrides) -> RecaptchaService:
    defaults = {
        'enabled': True,
        'project_id': 'proj',
        'site_key': 'site',
        'score_threshold': 0.5,
    }
    defaults.update(overrides)
    return RecaptchaService(**defaults)


def test_verify_passes_when_disabled():
    service = RecaptchaService(enabled=False)
    ok, err = service.verify(None, action='login')
    assert ok is True
    assert err is None


def test_verify_fails_when_enabled_but_unconfigured():
    service = RecaptchaService(enabled=True, project_id='', site_key='')
    ok, err = service.verify('token', action='login')
    assert ok is False
    assert 'unavailable' in err


def test_verify_requires_token_when_enabled():
    service = _enabled_service()
    ok, err = service.verify(None, action='login')
    assert ok is False
    assert 'token is required' in err


def test_verify_requires_action_when_enabled():
    service = _enabled_service()
    ok, err = service.verify('token', action='  ')
    assert ok is False
    assert 'failed' in err


def test_verify_fails_when_assessment_raises():
    service = _enabled_service()
    with patch.object(service, 'create_assessment', side_effect=RuntimeError('boom')):
        ok, err = service.verify('token', action='login')
    assert ok is False
    assert 'failed' in err


def test_verify_fails_when_assessment_is_none():
    service = _enabled_service()
    with patch.object(service, 'create_assessment', return_value=None):
        ok, err = service.verify('token', action='login')
    assert ok is False


def test_verify_fails_when_score_below_threshold():
    service = _enabled_service(score_threshold=0.7)
    assessment = SimpleNamespace(
        risk_analysis=SimpleNamespace(score=0.2),
        token_properties=SimpleNamespace(action='login'),
    )
    with patch.object(service, 'create_assessment', return_value=assessment):
        ok, err = service.verify('token', action='login')
    assert ok is False


def test_verify_succeeds_when_score_meets_threshold():
    service = _enabled_service(score_threshold=0.5)
    assessment = SimpleNamespace(
        risk_analysis=SimpleNamespace(score=0.9),
        token_properties=SimpleNamespace(action='login'),
    )
    with patch.object(service, 'create_assessment', return_value=assessment):
        ok, err = service.verify('token', action='login')
    assert ok is True
    assert err is None


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('true', True),
        ('1', True),
        ('yes', True),
        ('on', True),
        ('false', False),
        (0, False),
    ],
)
def test_as_bool_parses_common_strings(raw, expected):
    assert RecaptchaService._as_bool(raw) is expected
