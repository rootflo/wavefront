"""What an app migration gets to work with, built from floware's config.ini.

This builds only the database and common containers, not ``floware.di``, which
would build the whole application and start its resources on import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dependency_injector import containers, providers
from dotenv import dotenv_values, load_dotenv

from common_module.common_container import CommonContainer
from common_module.config_loader import load_ini
from common_module.feature.feature_flag import FeatureFlags
from common_module.security.secret_cipher import SecretCipher
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from flo_utils.envelope import EnvelopeCipher

FLOWARE_DIR = Path(__file__).resolve().parents[1]
CONFIG_INI = FLOWARE_DIR / 'config.ini'
DEFAULT_ENV_FILE = FLOWARE_DIR / '.env'


class AppMigrationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    db = providers.Container(DatabaseModuleContainer, config=config)
    common = providers.Container(
        CommonContainer,
        config=config,
        cache_manager=db.cache_manager,
    )


def build_container() -> AppMigrationContainer:
    container = AppMigrationContainer()
    load_ini(container.config, CONFIG_INI)
    return container


def load_env_file(env_file: Path) -> None:
    """Use the env file's settings, even over variables exported in the shell.

    A profile still exporting old values (CLOUD_PROVIDER=gcp,
    APPLICATION_BUCKET=flo-web, real AWS keys) would otherwise silently point
    a migration's writes at the wrong bucket, database or KMS key. Deployed
    images have no env file, so their environment is used as is.
    """
    if not env_file.is_file():
        print(f'No env file at {env_file}; using the exported environment')
        return
    shadowed = [
        key
        for key, value in dotenv_values(env_file).items()
        if key in os.environ and os.environ[key] != value
    ]
    load_dotenv(env_file, override=True)
    print(f'Loaded settings from {env_file}')
    if shadowed:
        print(
            f'  overrode {len(shadowed)} exported var(s) with the env file: '
            f'{", ".join(sorted(shadowed))}'
        )


class AppMigrationContext:
    """Handed to each migration's ``upgrade`` and ``verify``.

    Everything is built on first use, so ``status`` and migrations that do not
    need them never touch KMS, the bucket or Redis.
    """

    def __init__(self, container: AppMigrationContainer, dry_run: bool):
        self.dry_run = dry_run
        self._container = container
        self._envelope: Optional[EnvelopeCipher] = None

    @property
    def config(self) -> dict:
        return self._container.config()

    @property
    def app_version(self) -> Optional[str]:
        return self.config.get('telemetry', {}).get('app_version')

    @property
    def feature_flags(self) -> FeatureFlags:
        return self._container.common.feature_flags()

    @property
    def db_client(self) -> DatabaseClient:
        return self._container.db.db_client()

    @property
    def bucket(self) -> str:
        return self.config['storage']['application_bucket']

    @property
    def cloud_storage(self) -> CloudStorageManager:
        return self._container.common.cloud_storage_manager()

    @property
    def secret_cipher(self) -> SecretCipher:
        """Encrypts only with ENVELOPE_ENCRYPTION_ENABLED on, like the app."""
        return self._container.common.secret_cipher()

    @property
    def cache_manager(self) -> CacheManager:
        return self._container.db.cache_manager()

    def envelope(self) -> EnvelopeCipher:
        """The envelope cipher on the configured KMS key; contacts KMS when used."""
        if self._envelope is None:
            self._envelope = EnvelopeCipher(
                kms_cipher=self._container.common.kms_cipher()
            )
        return self._envelope

    def envelope_secret_cipher(self) -> SecretCipher:
        """A SecretCipher that encrypts and decrypts whatever the flag says.

        `secret_cipher` follows ENVELOPE_ENCRYPTION_ENABLED, and with it off
        rejects encrypted values, so a downgrade run with the flag already off
        could not decrypt them.
        """
        return SecretCipher(enabled=True, envelope_factory=self.envelope)
