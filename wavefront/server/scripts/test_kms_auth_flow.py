#!/usr/bin/env python3
"""
Simulate /floconsole/v1/authenticate token create + require_auth decode (KMS).

Usage:
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
  export GCP_PROJECT_ID=... GCP_LOCATION=... GCP_KMS_KEY_RING=...
  export GCP_KMS_CRYPTO_KEY=... GCP_KMS_CRYPTO_KEY_VERSION=...
  uv run python scripts/test_kms_auth_flow.py
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../packages/flo_cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../apps/floconsole'))

from flo_cloud.gcp.kms import GcpKMS
from flo_cloud.kms import FloKmsService
from floconsole.constants.auth import AUTH_ROLE_ID
from floconsole.services.token_service import TokenAlgorithms, TokenService

ISSUER = os.getenv('CONSOLE_JWT_ISSUER', 'https://floconsole.rootflo.ai')
AUDIENCE = os.getenv('CONSOLE_JWT_AUDIENCE', 'https://floconsole.rootflo.ai')
PREFIX = os.getenv('CONSOLE_TOKEN_PREFIX', 'fc_')


def _dummy_pem_keys() -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as priv:
        subprocess.run(
            ['openssl', 'genrsa', '-out', priv.name, '2048'],
            check=True,
            capture_output=True,
        )
        priv_pem = open(priv.name, 'rb').read()
    pub_proc = subprocess.run(
        ['openssl', 'rsa', '-pubout'],
        input=priv_pem,
        capture_output=True,
        check=True,
    )
    return base64.b64encode(priv_pem).decode(), base64.b64encode(
        pub_proc.stdout
    ).decode()


def _simulate_require_auth(decoded: dict) -> str | None:
    """Mirror floconsole require_auth checks after decode_token."""
    if 'session_id' not in decoded:
        return 'Invalid token: missing session_id'
    if 'role_id' not in decoded or decoded['role_id'] != AUTH_ROLE_ID:
        return 'Invalid token: Not the console user'
    return None


def main() -> int:
    print('=== KMS auth flow test (create_token + decode_token) ===\n')

    for var in (
        'GCP_PROJECT_ID',
        'GCP_LOCATION',
        'GCP_KMS_KEY_RING',
        'GCP_KMS_CRYPTO_KEY',
        'GCP_KMS_CRYPTO_KEY_VERSION',
        'GOOGLE_APPLICATION_CREDENTIALS',
    ):
        print(f'  {var}={os.environ.get(var, "<not set>")}')

    print('\n--- Step 1: Init KMS (same as ApplicationContainer) ---')
    kms = FloKmsService(cloud_provider='gcp')
    gcp: GcpKMS = kms.kms_client  # type: ignore[assignment]
    print(f'  KMS key: {gcp.key_name}')
    print(f'  jwt_algorithm(): {kms.jwt_algorithm()}')
    print(f'  uses_pkcs1: {gcp._uses_pkcs1}')

    priv, pub = _dummy_pem_keys()
    token_service = TokenService(
        private_key=priv,
        public_key=pub,
        kms_service=kms,
        algorithm=TokenAlgorithms.PS256,
        app_env='production',
        token_prefix=PREFIX,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    print('\n--- Step 2: TokenService (production / KMS) ---')
    print(f'  is_dev={token_service.is_dev}')
    print(f'  algorithm={token_service.algorithm}')

    session_id = str(uuid4())
    user_id = str(uuid4())
    print('\n--- Step 3: create_token (POST /authenticate) ---')
    token = token_service.create_token(
        sub='admin@rootflo.ai',
        user_id=user_id,
        role_id=AUTH_ROLE_ID,
        payload={'session_id': session_id},
    )
    print(f'  token length={len(token)}')
    print(f'  prefix ok={token.startswith(PREFIX)}')
    header_alg = __import__('json').loads(
        base64.urlsafe_b64decode(token[len(PREFIX) :].split('.')[0] + '==')
    )['alg']
    print(f'  JWT header alg={header_alg}')

    print('\n--- Step 4: decode_token (require_auth middleware) ---')
    try:
        decoded = token_service.decode_token(token)
    except ValueError as e:
        print(f'  FAIL ValueError: {e}')
        return 1
    except Exception as e:
        print(f'  FAIL {type(e).__name__}: {e}')
        return 1

    print(f'  decoded session_id={decoded.get("session_id")}')
    print(f'  decoded role_id={decoded.get("role_id")}')
    print(f'  decoded iss={decoded.get("iss")}')

    err = _simulate_require_auth(decoded)
    if err:
        print('\n--- Step 5: require_auth ---')
        print(f'  FAIL: {err}')
        return 1

    print('\n--- Step 5: require_auth ---')
    print('  OK: token would be accepted')
    print('\n=== PASS: full KMS create + validate flow ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
