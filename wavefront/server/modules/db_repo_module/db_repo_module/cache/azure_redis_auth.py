import os

import redis
from redis_entraid.cred_provider import create_from_default_azure_credential

_patched = False


def patch_redis_for_azure() -> None:
    global _patched
    if _patched or os.getenv('CLOUD_PROVIDER', '').lower() != 'azure':
        return

    provider = create_from_default_azure_credential(
        ('https://redis.azure.com/.default',)
    )
    original_init = redis.ConnectionPool.__init__

    def patched_init(self, *args, **kw):
        kw.pop('password', None)
        kw.pop('username', None)
        kw['credential_provider'] = provider
        original_init(self, *args, **kw)

    redis.ConnectionPool.__init__ = patched_init
    _patched = True
