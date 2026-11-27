"""Every secret auth header is filtered from Sentry events.

common_module cannot import RootfloHeaders (this module depends on it), so
its Sentry denylist is written out by hand. This test keeps the two in step.
"""

from common_module.error_reporting.scrubbing import EXTRA_DENYLIST
from user_management_module.constants.auth import RootfloHeaders

# Not secret: they are replay protection, useful when debugging HMAC failures.
NOT_SECRET = {RootfloHeaders.TIMESTAMP, RootfloHeaders.NONCE}


def test_secret_auth_headers_are_in_the_sentry_denylist():
    headers = {
        value
        for name, value in vars(RootfloHeaders).items()
        if not name.startswith('_') and isinstance(value, str)
    }
    secret = headers - NOT_SECRET
    assert secret == {
        RootfloHeaders.CLIENT_KEY,
        RootfloHeaders.SIGNATURE,
        RootfloHeaders.PASSTHROUGH,
    }, 'A header was added to RootfloHeaders: decide whether it is secret.'

    for header in secret:
        lowered = header.lower()
        assert lowered in EXTRA_DENYLIST
        assert lowered.replace('-', '_') in EXTRA_DENYLIST
