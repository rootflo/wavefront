from unittest.mock import Mock

from user_management_module.utils.rate_limit import password_reset_rate_limited


def test_password_reset_rate_limited_cooldown():
    cache = Mock()
    cache.add.return_value = False

    assert password_reset_rate_limited(
        cache,
        {
            'auth': {
                'password_reset_cooldown_seconds': '60',
                'password_reset_max_per_email': '3',
                'password_reset_rate_window_seconds': '3600',
            }
        },
        'user@example.com',
    )
    cache.incr_with_expiry.assert_not_called()


def test_password_reset_rate_limited_hourly_cap():
    cache = Mock()
    cache.add.return_value = True
    cache.incr_with_expiry.return_value = 4

    assert password_reset_rate_limited(
        cache,
        {
            'auth': {
                'password_reset_cooldown_seconds': '60',
                'password_reset_max_per_email': '3',
                'password_reset_rate_window_seconds': '3600',
            }
        },
        'user@example.com',
    )


def test_password_reset_rate_limited_allows_under_cap():
    cache = Mock()
    cache.add.return_value = True
    cache.incr_with_expiry.return_value = 1

    assert not password_reset_rate_limited(
        cache,
        {
            'auth': {
                'password_reset_cooldown_seconds': '60',
                'password_reset_max_per_email': '3',
                'password_reset_rate_window_seconds': '3600',
            }
        },
        'user@example.com',
    )
