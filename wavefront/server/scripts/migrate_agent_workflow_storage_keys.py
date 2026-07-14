"""
One-time backfill: copy existing agent/workflow YAML files from the old flat
storage key (agents/{namespace}/{name}.yaml) to the new versioned key
(agents/{namespace}/{name}/{version}.yaml), matching the version=1 rows the
Alembic migration (2026_07_09_1151-1d6a0d5cfd6f_add_agent_workflow_versioning)
backfills into agent_versions/workflow_versions.

Idempotent: skips any row whose new-format key already exists, so it's safe
to re-run. Leaves the old flat-path objects in place - unreferenced but
harmless once the app is deployed with the versioned key format.

Run once, after applying the DB migration and before/alongside deploying the
code that switches agent_utils.get_agent_yaml_key / workflow_utils.get_workflow_yaml_key
to the versioned format.

Usage:
    cd wavefront/server
    uv run python scripts/migrate_agent_workflow_storage_keys.py

Required environment variables (same as alembic/env.py and celery_worker/env.py):
    DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    CLOUD_PROVIDER, AGENT_YAML_BUCKET
"""

import asyncio
import os

from dotenv import load_dotenv

from db_repo_module.database.connection import DatabaseClient, DatabaseConfig
from db_repo_module.models.agent import Agent
from db_repo_module.models.workflow import Workflow
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError


async def migrate_entity(
    entity_label: str,
    rows: list,
    old_key_fn,
    new_key_fn,
    cloud_storage_manager: CloudStorageManager,
    bucket_name: str,
) -> None:
    copied, skipped, missing = 0, 0, 0

    for row in rows:
        old_key = old_key_fn(row.namespace, row.name)
        new_key = new_key_fn(row.namespace, row.name, row.current_version)

        try:
            cloud_storage_manager.read_file(bucket_name, new_key)
            skipped += 1
            continue
        except CloudStorageFileNotFoundError:
            pass

        try:
            yaml_bytes = cloud_storage_manager.read_file(bucket_name, old_key)
        except CloudStorageFileNotFoundError:
            print(
                f'  [missing] {entity_label} {row.namespace}/{row.name}: no file at {old_key}'
            )
            missing += 1
            continue

        cloud_storage_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=bucket_name, key=new_key
        )
        print(f'  [copied] {old_key} -> {new_key}')
        copied += 1

    print(
        f'{entity_label}: {copied} copied, {skipped} already migrated, {missing} missing source file'
    )


async def main() -> None:
    load_dotenv()

    db_config = DatabaseConfig(
        username=os.environ['DB_USERNAME'],
        password=os.environ['DB_PASSWORD'],
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT'],
        db_name=os.environ['DB_NAME'],
    )
    db_client = DatabaseClient(db_config=db_config)

    cloud_storage_manager = CloudStorageManager(provider=os.environ['CLOUD_PROVIDER'])
    bucket_name = os.environ['AGENT_YAML_BUCKET']

    agent_repository = SQLAlchemyRepository[Agent](model=Agent, db_client=db_client)
    workflow_repository = SQLAlchemyRepository[Workflow](
        model=Workflow, db_client=db_client
    )

    agents = await agent_repository.find(limit=1_000_000)
    workflows = await workflow_repository.find(limit=1_000_000)

    print(f'Found {len(agents)} agents, {len(workflows)} workflows')

    await migrate_entity(
        'agent',
        agents,
        old_key_fn=lambda namespace, name: f'agents/{namespace}/{name}.yaml',
        new_key_fn=lambda namespace,
        name,
        version: f'agents/{namespace}/{name}/{version}.yaml',
        cloud_storage_manager=cloud_storage_manager,
        bucket_name=bucket_name,
    )
    await migrate_entity(
        'workflow',
        workflows,
        old_key_fn=lambda namespace, name: f'workflows/{namespace}/{name}.yaml',
        new_key_fn=lambda namespace,
        name,
        version: f'workflows/{namespace}/{name}/{version}.yaml',
        cloud_storage_manager=cloud_storage_manager,
        bucket_name=bucket_name,
    )

    await db_client.close()


if __name__ == '__main__':
    asyncio.run(main())
