"""Seed required config.ini env vars before test modules import settings.

Locally setup.sh copies celery_worker/.env.sample → .env and settings loads
it. CI has no .env, so import-time load_ini(envs_required=True) would fail.
setdefault keeps real CI/local env values when present.
"""

from __future__ import annotations

import os

# Mirrors celery_worker/.env.sample (required keys only; rest have ini defaults).
for _key, _value in {
    'DB_NAME': 'floware',
    'DB_USERNAME': 'postgres',
    'DB_PASSWORD': 'postgres',
    'DB_HOST': 'localhost',
    'DB_PORT': '5432',
    'CLOUD_PROVIDER': 'aws',
}.items():
    os.environ.setdefault(_key, _value)
