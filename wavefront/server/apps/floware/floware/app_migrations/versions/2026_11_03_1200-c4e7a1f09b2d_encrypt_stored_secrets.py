"""Envelope-encrypt stored secrets

Applies once ENVELOPE_ENCRYPTION_ENABLED is on. Moves literal secrets out of
API-service YAML into the `secrets` table, encrypts every plaintext secret,
then flushes Redis keys that may still cache the plaintext.

`downgrade` decrypts every stored secret and flushes the same caches. YAML
keeps its ${secrets.NAME} references: they resolve from the `secrets` rows,
plaintext once decrypted, so they work with the flag off too.
"""

from typing import List

from sqlalchemy import select

from common_module.feature.feature_flag import FeatureFlags
from db_repo_module.models.api_services import ApiServices
from floware.app_migrations import secret_conversion as sc
from floware.app_migrations.context import AppMigrationContext

revision = 'c4e7a1f09b2d'
down_revision = None
description = 'Envelope-encrypt stored secrets'
# With the flag on, every secret read fails on plaintext until this has run.
blocking = True


def applies(flags: FeatureFlags) -> bool:
    return flags.envelope_encryption_enabled


async def upgrade(ctx: AppMigrationContext) -> dict:
    # Before converting anything: a wrong key or missing permission should not
    # surface halfway through.
    if not sc.kms_reachable(ctx.envelope):
        raise RuntimeError('KMS encrypt/decrypt round trip failed')

    prefix = '[dry-run] ' if ctx.dry_run else ''
    cipher = ctx.envelope_secret_cipher()
    rewritten, created = await sc.extract_yaml_literals(
        ctx.db_client, ctx.cloud_storage, ctx.bucket, cipher, ctx.dry_run
    )
    print(
        f'{prefix}api_services YAML: {rewritten} rewritten, {created} secrets created'
    )

    conv = sc.Converter(sc.ENCRYPT, None, cipher, ctx.envelope, ctx.dry_run)
    reports = await sc.convert_tables(ctx.db_client, conv, ctx.dry_run)
    for table, report in reports.items():
        print(
            f'{prefix}{table}: {report.changed} encrypted, '
            f'{report.already} already done'
        )

    sc.flush_caches(ctx.dry_run)
    return {
        'api_services_yaml': {'rewritten': rewritten, 'secrets_created': created},
        'tables': {
            table: {'encrypted': report.changed, 'already': report.already}
            for table, report in reports.items()
        },
    }


async def verify(ctx: AppMigrationContext) -> List[str]:
    conv = sc.Converter(
        sc.VERIFY, 'encrypted', ctx.envelope_secret_cipher(), ctx.envelope, dry_run=True
    )
    reports = await sc.convert_tables(ctx.db_client, conv, dry_run=True)
    problems = [
        f'{label} not encrypted'
        for report in reports.values()
        for label in report.mismatched
    ]

    async with ctx.db_client.session() as session:
        services = (await session.execute(select(ApiServices))).scalars().all()
    problems += [
        f'{item}: literal secret'
        for item in sc.verify_yaml(ctx.cloud_storage, ctx.bucket, services)
    ]
    return problems


async def downgrade(ctx: AppMigrationContext) -> dict:
    if not sc.kms_reachable(ctx.envelope):
        raise RuntimeError('KMS encrypt/decrypt round trip failed')

    prefix = '[dry-run] ' if ctx.dry_run else ''
    cipher = ctx.envelope_secret_cipher()
    conv = sc.Converter(sc.DECRYPT, None, cipher, ctx.envelope, ctx.dry_run)
    reports = await sc.convert_tables(ctx.db_client, conv, ctx.dry_run)
    for table, report in reports.items():
        print(
            f'{prefix}{table}: {report.changed} decrypted, '
            f'{report.already} already done'
        )

    if not ctx.dry_run:
        check = sc.Converter(sc.VERIFY, 'plaintext', cipher, ctx.envelope, True)
        leftovers = [
            label
            for report in (
                await sc.convert_tables(ctx.db_client, check, dry_run=True)
            ).values()
            for label in report.mismatched
        ]
        if leftovers:
            raise RuntimeError(
                f'{len(leftovers)} value(s) still encrypted: {", ".join(leftovers[:20])}'
            )

    sc.flush_caches(ctx.dry_run)
    return {
        'tables': {
            table: {'decrypted': report.changed, 'already': report.already}
            for table, report in reports.items()
        },
    }
