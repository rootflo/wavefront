"""Convert stored secrets between plaintext and envelope encryption.

The `encrypt_stored_secrets` app migration uses the encrypt and verify paths;
decrypt, rewrap and YAML inlining are for operator tooling. Every function is
safe to re-run: values already in the target form are skipped.

Covered: datasource.config, authenticator.config, llm_inference_config.api_key,
stt_configs.api_key, tts_configs.api_key, telephony_configs.credentials,
auth_secrets.client_secret, secrets.value and API-service YAML in the bucket.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import yaml
from sqlalchemy import select

from api_services_module.secrets.references import (
    find_literal_secrets,
    find_refs,
    iter_secret_fields,
    make_ref,
    replace_literals_with_refs,
    substitute,
)
from common_module.security.secret_cipher import SecretCipher
from datasource.types import get_datasource_secret_fields
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.redis_settings import RedisSettings
from db_repo_module.database.connection import DatabaseClient
from db_repo_module.models.api_services import ApiServices
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.secret import Secret
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.models.tts_config import TtsConfig
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from flo_utils.envelope import EnvelopeCipher
from plugins_module.utils.authenticator_helper import get_authenticator_secret_fields
from voice_agents_module.utils.telephony_secrets import telephony_secret_fields

ENCRYPT, DECRYPT, VERIFY, REWRAP = 'encrypt', 'decrypt', 'verify', 'rewrap'

# The app migration (versions/) that runs ENCRYPT on every deployment.
ENCRYPT_MIGRATION_REVISION = 'c4e7a1f09b2d'

# Cache keys that may hold secrets in their old form, per namespace.
FLOWARE_CACHE_PATTERNS = (
    'llm_inference_config*',
    'stt_config*',
    'tts_config*',
    'telephony_config*',
    'api_services/*',
)
CALL_PROCESSING_CACHE_PATTERNS = (
    'llm_inference_config:*',
    'stt_config:*',
    'tts_config:*',
    'telephony_config:*',
)


@dataclass
class Report:
    changed: int = 0
    already: int = 0
    mismatched: List[str] = field(default_factory=list)


class Converter:
    """Applies one mode to a single stored value and records the outcome."""

    def __init__(
        self,
        mode: str,
        verify_mode: Optional[str],
        cipher: SecretCipher,
        envelope: Callable[[], EnvelopeCipher],
        dry_run: bool,
    ):
        self.mode = mode
        self.verify_mode = verify_mode
        self.cipher = cipher
        self.envelope = envelope
        self.dry_run = dry_run

    def scalar(self, value: Optional[str], label: str, report: Report) -> Optional[str]:
        return self._convert(value, label, report, as_json=False)

    def json_value(self, value: Any, label: str, report: Report) -> Any:
        return self._convert(value, label, report, as_json=True)

    def fields(
        self, config: Dict[str, Any], fields: Iterable[str], label: str, report: Report
    ) -> Dict[str, Any]:
        result = dict(config)
        for name in fields:
            if result.get(name) is not None:
                result[name] = self.json_value(result[name], f'{label}.{name}', report)
        return result

    def _convert(self, value: Any, label: str, report: Report, as_json: bool) -> Any:
        if value is None or value == '':
            return value
        encrypted = SecretCipher.is_encrypted(value)

        if self.mode == VERIFY:
            if encrypted != (self.verify_mode == 'encrypted'):
                report.mismatched.append(label)
            return value

        if self.mode == ENCRYPT:
            if encrypted:
                report.already += 1
                return value
            report.changed += 1
            if self.dry_run:
                return value
            return (
                self.cipher.protect_json(value)
                if as_json
                else self.cipher.protect(value)
            )

        if self.mode == DECRYPT:
            if not encrypted:
                report.already += 1
                return value
            report.changed += 1
            if self.dry_run:
                return value
            return (
                self.cipher.reveal_json(value) if as_json else self.cipher.reveal(value)
            )

        # REWRAP
        if not encrypted:
            report.mismatched.append(label)
            return value
        report.changed += 1
        if self.dry_run:
            return value
        return self.envelope().rewrap(value)


# ---- tables ---------------------------------------------------------------


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


TableHandler = Callable[[Any, Converter, Report], None]


def _datasource(row: Datasource, conv: Converter, report: Report) -> None:
    fields = get_datasource_secret_fields(row.type)
    if fields:
        row.config = conv.fields(
            _as_dict(row.config), fields, f'datasource {row.id}', report
        )


def _authenticator(row: Authenticator, conv: Converter, report: Report) -> None:
    fields = get_authenticator_secret_fields(row.auth_type)
    if fields:
        row.config = conv.fields(
            _as_dict(row.config), fields, f'authenticator {row.auth_id}', report
        )


def _telephony(row: TelephonyConfig, conv: Converter, report: Report) -> None:
    fields = telephony_secret_fields(row.provider)
    if fields:
        credentials = conv.fields(
            _as_dict(row.credentials), fields, f'telephony_config {row.id}', report
        )
        row.credentials = json.dumps(credentials)


def _scalar(attr: str, label: str) -> TableHandler:
    def handle(row: Any, conv: Converter, report: Report) -> None:
        setattr(
            row,
            attr,
            conv.scalar(getattr(row, attr), f'{label} {row.id}.{attr}', report),
        )

    return handle


TABLES: Tuple[Tuple[str, Any, TableHandler], ...] = (
    ('datasource', Datasource, _datasource),
    ('authenticator', Authenticator, _authenticator),
    (
        'llm_inference_config',
        LlmInferenceConfig,
        _scalar('api_key', 'llm_inference_config'),
    ),
    ('stt_configs', SttConfig, _scalar('api_key', 'stt_config')),
    ('tts_configs', TtsConfig, _scalar('api_key', 'tts_config')),
    ('telephony_configs', TelephonyConfig, _telephony),
    ('auth_secrets', AuthSecrets, _scalar('client_secret', 'auth_secrets')),
    ('secrets', Secret, _scalar('value', 'secrets')),
)


async def convert_tables(
    db_client: DatabaseClient, conv: Converter, dry_run: bool
) -> Dict[str, Report]:
    reports: Dict[str, Report] = {}
    for table, model, handle in TABLES:
        report = Report()
        # One transaction per table; a failure rolls back only that table.
        async with db_client.session() as session:
            rows = (await session.execute(select(model))).scalars().all()
            for row in rows:
                handle(row, conv, report)
            if dry_run or conv.mode == VERIFY:
                await session.rollback()
            else:
                await session.commit()
        reports[table] = report
    return reports


# ---- API-service YAML -----------------------------------------------------


def _secret_name(service_id: str, path: str, taken: set) -> str:
    tail = path.removeprefix('service.')
    base = re.sub(r'[^A-Z0-9]+', '_', f'APISVC_{service_id}_{tail}'.upper()).strip('_')
    base = base[:120]
    name, suffix = base, 2
    while name in taken:
        name = f'{base}_{suffix}'
        suffix += 1
    taken.add(name)
    return name


def _service_path(service: ApiServices) -> str:
    """Where the runtime reads this service's YAML (ApiServicesManager).

    Not `service_def_path`: the runtime ignores it, so converting a file it
    names would leave the one actually served untouched.
    """
    return f'api_services/{service.id}.yaml'


def _read_service_yaml(
    storage: CloudStorageManager, bucket: str, service_id: str, path: str
) -> Optional[Any]:
    """The service's YAML, or None when the bucket has no file at `path`.

    A row whose definition is gone holds no secrets to convert; skipping it
    keeps one dangling row from failing the whole run.
    """
    try:
        return yaml.safe_load(storage.read_file(bucket, path).decode('utf-8'))
    except CloudStorageFileNotFoundError:
        print(f'  [yaml] {service_id}: no definition at {path}, skipped')
        return None


async def extract_yaml_literals(
    db_client: DatabaseClient,
    storage: CloudStorageManager,
    bucket: str,
    cipher: SecretCipher,
    dry_run: bool,
) -> Tuple[int, int]:
    """Move literal secrets from API-service YAML into `secrets` (--encrypt only).

    Returns (services rewritten, secrets created).
    """
    async with db_client.session() as session:
        services = (await session.execute(select(ApiServices))).scalars().all()
        existing = (await session.execute(select(Secret))).scalars().all()
    # Plain values, not ORM objects: those expire on commit, after their
    # session is gone.
    by_name: Dict[str, str] = {secret.name: secret.value for secret in existing}
    taken = set(by_name)

    rewritten, created = 0, 0
    for service in services:
        path = _service_path(service)
        document = _read_service_yaml(storage, bucket, service.id, path)
        if document is None:
            continue
        literals = []
        for field_path, value in find_literal_secrets(document):
            # Moving these into a secret would store the reference as text;
            # left in place, verify reports them for a fix by hand
            if find_refs(value):
                print(
                    f'  [yaml] {service.id} {field_path}: mixes literal text with a '
                    'secret reference, skipped'
                )
                continue
            literals.append((field_path, value))
        if not literals:
            continue

        mapping: Dict[str, str] = {}
        new_secrets: List[Secret] = []
        new_values: Dict[str, str] = {}
        for field_path, value in literals:
            value = str(value)
            name = _reuse_name(service.id, field_path, value, by_name, cipher, dry_run)
            if name is None:
                name = _secret_name(service.id, field_path, taken)
                stored_value = value if dry_run else cipher.protect(value)
                new_secrets.append(
                    Secret(
                        name=name,
                        description=f'Extracted from API service {service.id} ({field_path})',
                        value=stored_value,
                    )
                )
                new_values[name] = stored_value
            mapping[field_path] = name
            print(f'  [yaml] {service.id} {field_path} -> {make_ref(name)}')

        rewritten += 1
        created += len(new_secrets)
        if dry_run:
            continue

        # Secrets first, then the YAML: a crash in between leaves unused
        # secrets (reused on re-run), never a YAML pointing at a missing one.
        async with db_client.session() as session:
            session.add_all(new_secrets)
            await session.commit()
        by_name.update(new_values)
        updated = replace_literals_with_refs(document, mapping)
        storage.save_small_file(
            file_content=yaml.safe_dump(updated, sort_keys=False).encode('utf-8'),
            bucket_name=bucket,
            key=path,
            content_type='application/yaml',
        )
    return rewritten, created


def _reuse_name(
    service_id: str,
    field_path: str,
    value: str,
    by_name: Dict[str, str],
    cipher: SecretCipher,
    dry_run: bool,
) -> Optional[str]:
    """Reuse a secret an earlier, interrupted run already created for this field."""
    prefix = re.sub(
        r'[^A-Z0-9]+',
        '_',
        f'APISVC_{service_id}_{field_path.removeprefix("service.")}'.upper(),
    ).strip('_')[:120]
    for name, stored in by_name.items():
        if name == prefix or name.startswith(f'{prefix}_'):
            if cipher.is_encrypted(stored) and dry_run:
                continue  # a dry run never calls KMS
            plain = cipher.reveal(stored) if cipher.is_encrypted(stored) else stored
            if plain == value:
                return name
    return None


async def inline_yaml_refs(
    db_client: DatabaseClient,
    storage: CloudStorageManager,
    bucket: str,
    cipher: SecretCipher,
    dry_run: bool,
) -> Tuple[int, List[str]]:
    """Replace ${secrets.NAME} in API-service YAML with the secret's plaintext.

    The reverse of the extraction --encrypt does; `secrets` rows are kept.
    A service referencing an unknown secret is reported and left untouched.
    Returns (services rewritten, problems).
    """
    async with db_client.session() as session:
        services = (await session.execute(select(ApiServices))).scalars().all()
        stored = {
            secret.name: secret.value
            for secret in (await session.execute(select(Secret))).scalars().all()
        }

    rewritten, problems = 0, []
    for service in services:
        path = _service_path(service)
        document = _read_service_yaml(storage, bucket, service.id, path)
        if document is None:
            continue
        fields = [
            (field_path, parent, key)
            for field_path, parent, key, _sensitive in iter_secret_fields(document)
            if find_refs(parent[key])
        ]
        if not fields:
            continue

        names = set().union(*(find_refs(parent[key]) for _p, parent, key in fields))
        unknown = sorted(names - stored.keys())
        if unknown:
            problems.append(f'api_service {service.id}: unknown {", ".join(unknown)}')
            continue

        for field_path, _parent, _key in fields:
            print(f'  [yaml] {service.id} {field_path} <- inline value')
        rewritten += 1
        if dry_run:
            continue  # a dry run never calls KMS

        resolved = {
            name: cipher.reveal(stored[name])
            if cipher.is_encrypted(stored[name])
            else stored[name]
            for name in names
        }
        for _field_path, parent, key in fields:
            parent[key] = substitute(parent[key], resolved)
        storage.save_small_file(
            file_content=yaml.safe_dump(document, sort_keys=False).encode('utf-8'),
            bucket_name=bucket,
            key=path,
            content_type='application/yaml',
        )
    return rewritten, problems


def verify_yaml(storage: CloudStorageManager, bucket: str, services) -> List[str]:
    """Literal secrets left in API-service YAML (only valid with encryption on)."""
    found = []
    for service in services:
        path = _service_path(service)
        document = _read_service_yaml(storage, bucket, service.id, path)
        if document is None:
            continue
        found += [
            f'api_service {service.id} {p}' for p, _ in find_literal_secrets(document)
        ]
    return found


# ---- Redis ----------------------------------------------------------------


def flush_caches(dry_run: bool) -> None:
    targets = (
        (
            os.environ.get('APP_NAME') or 'floware',
            os.environ.get('REDIS_DB', '0'),
            FLOWARE_CACHE_PATTERNS,
        ),
        (
            os.environ.get('CALL_PROCESSING_APP_NAME') or 'call_processing',
            os.environ.get('CALL_PROCESSING_REDIS_DB')
            or os.environ.get('REDIS_DB', '0'),
            CALL_PROCESSING_CACHE_PATTERNS,
        ),
    )
    for namespace, db, patterns in targets:
        if dry_run:
            print(f'  [cache] would flush {namespace}/{{{",".join(patterns)}}}')
            continue
        cache = CacheManager(
            namespace=namespace,
            settings=RedisSettings(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=os.environ.get('REDIS_PORT', '6379'),
                protocol=os.environ.get('REDIS_PROTOCOL', 'redis'),
                password=os.environ.get('REDIS_PASSWORD') or None,
                db=db,
            ),
        )
        deleted = sum(cache.invalidate_query(pattern) for pattern in patterns)
        print(f'  [cache] {namespace}: {deleted} keys flushed')


def kms_reachable(envelope: Callable[[], EnvelopeCipher]) -> bool:
    try:
        cipher = envelope()
        cipher.decrypt(cipher.encrypt('kms-probe'))
    except Exception as e:
        print(f'KMS: round trip failed: {e!r}')
        return False
    print('KMS: round trip ok')
    return True
