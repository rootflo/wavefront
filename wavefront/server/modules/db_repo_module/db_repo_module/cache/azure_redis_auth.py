import os
import threading

import redis

_patched = False


def patch_redis_for_azure() -> None:
    global _patched
    if _patched or os.getenv('CLOUD_PROVIDER', '').lower() != 'azure':
        return

    from redis_entraid.cred_provider import create_from_default_azure_credential
    from redis.credentials import CredentialProvider

    _inner = create_from_default_azure_credential(('https://redis.azure.com/.default',))

    class _TimedProvider(CredentialProvider):
        def get_credentials(self):
            result = []
            exc = []

            def _fetch():
                try:
                    result.append(_inner.get_credentials())
                except Exception as e:
                    exc.append(e)

            t = threading.Thread(target=_fetch, daemon=True)
            t.start()
            t.join(timeout=10)
            if t.is_alive():
                raise TimeoutError('Azure Redis token fetch timed out after 10s')
            if exc:
                raise exc[0]
            return result[0]

    provider = _TimedProvider()
    original_init = redis.ConnectionPool.__init__

    def patched_init(self, *args, **kw):
        kw.pop('password', None)
        kw.pop('username', None)
        kw['credential_provider'] = provider
        original_init(self, *args, **kw)

    redis.ConnectionPool.__init__ = patched_init
    _patched = True
