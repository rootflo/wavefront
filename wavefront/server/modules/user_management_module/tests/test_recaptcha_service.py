"""Unit tests for RecaptchaService.verify branches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_verify_passes_when_disabled():
    service = RecaptchaService(enabled=False)
    ok, err = await service.verify(None, action='login')
    assert ok is True
    assert err is None


@pytest.mark.asyncio
async def test_verify_fails_when_enabled_but_unconfigured():
    service = RecaptchaService(enabled=True, project_id='', site_key='')
    ok, err = await service.verify('token', action='login')
    assert ok is False
    assert 'unavailable' in err


@pytest.mark.asyncio
async def test_verify_requires_token_when_enabled():
    service = _enabled_service()
    ok, err = await service.verify(None, action='login')
    assert ok is False
    assert 'token is required' in err


@pytest.mark.asyncio
async def test_verify_requires_action_when_enabled():
    service = _enabled_service()
    ok, err = await service.verify('token', action='  ')
    assert ok is False
    assert 'failed' in err


@pytest.mark.asyncio
async def test_verify_fails_when_assessment_raises():
    service = _enabled_service()
    with patch.object(
        service,
        'create_assessment',
        new_callable=AsyncMock,
        side_effect=RuntimeError('boom'),
    ) as create_assessment:
        ok, err = await service.verify('token', action='login')
    assert ok is False
    assert 'failed' in err
    create_assessment.assert_awaited_once_with(
        project_id='proj',
        recaptcha_key='site',
        token='token',
        recaptcha_action='login',
    )


@pytest.mark.asyncio
async def test_verify_fails_when_assessment_is_none():
    service = _enabled_service()
    with patch.object(
        service, 'create_assessment', new_callable=AsyncMock, return_value=None
    ) as create_assessment:
        ok, err = await service.verify('token', action='login')
    assert ok is False
    create_assessment.assert_awaited_once_with(
        project_id='proj',
        recaptcha_key='site',
        token='token',
        recaptcha_action='login',
    )


@pytest.mark.asyncio
async def test_verify_fails_when_score_below_threshold():
    service = _enabled_service(score_threshold=0.7)
    assessment = SimpleNamespace(
        risk_analysis=SimpleNamespace(score=0.2),
        token_properties=SimpleNamespace(action='login'),
    )
    with patch.object(
        service, 'create_assessment', new_callable=AsyncMock, return_value=assessment
    ) as create_assessment:
        ok, err = await service.verify('token', action='login')
    assert ok is False
    create_assessment.assert_awaited_once_with(
        project_id='proj',
        recaptcha_key='site',
        token='token',
        recaptcha_action='login',
    )


@pytest.mark.asyncio
async def test_verify_succeeds_when_score_meets_threshold():
    service = _enabled_service(score_threshold=0.5)
    assessment = SimpleNamespace(
        risk_analysis=SimpleNamespace(score=0.9),
        token_properties=SimpleNamespace(action='login'),
    )
    with patch.object(
        service, 'create_assessment', new_callable=AsyncMock, return_value=assessment
    ) as create_assessment:
        ok, err = await service.verify('token', action='login')
    assert ok is True
    assert err is None
    create_assessment.assert_awaited_once_with(
        project_id='proj',
        recaptcha_key='site',
        token='token',
        recaptcha_action='login',
    )


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


@pytest.mark.parametrize('value', [None, '', 'not-a-number', object()])
def test_as_float_falls_back_to_default_for_absent_or_non_numeric(value):
    assert RecaptchaService._as_float(value, 0.5) == 0.5


@pytest.mark.parametrize('value', [0.0, 0.5, 1.0, '0.25'])
def test_as_float_accepts_inclusive_unit_interval(value):
    parsed = RecaptchaService._as_float(value, 0.5)
    assert 0.0 <= parsed <= 1.0


@pytest.mark.parametrize('value', [-0.1, 1.1, float('nan'), float('inf'), '-inf'])
def test_as_float_rejects_non_finite_or_out_of_range(value):
    with pytest.raises(ValueError, match='score_threshold'):
        RecaptchaService._as_float(value, 0.5)


def test_enabled_service_fails_closed_on_invalid_threshold():
    with pytest.raises(ValueError, match='score_threshold'):
        RecaptchaService(
            enabled=True, project_id='p', site_key='s', score_threshold=2.0
        )
