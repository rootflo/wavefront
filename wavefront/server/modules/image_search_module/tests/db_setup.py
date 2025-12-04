"""
Database setup utilities for IKB functionality.
Can be imported and used in tests or other scripts.
"""

from typing import Optional
from db_repo_module.database.connection import DatabaseClient, DatabaseConfig
from db_repo_module.database.base import Base
from sqlalchemy import text


async def ensure_tables_exist(db_client: DatabaseClient) -> None:
    """
    Ensure all IKB-related tables exist in the database with the correct schema.
    This will drop and recreate tables to ensure they have the latest schema.

    Args:
        db_client: DatabaseClient instance
    """
    async with db_client._engine.begin() as connection:
        # Drop existing tables in reverse order (due to foreign key constraints)
        tables_to_drop = [
            'sift_features',
            'reference_image_features',
            'image_knowledge_bases',
        ]

        for table in tables_to_drop:
            await connection.execute(text(f'DROP TABLE IF EXISTS {table} CASCADE;'))

        # Create all tables with the latest schema
        await connection.run_sync(Base.metadata.create_all)


async def setup_test_database(
    db_config: Optional[DatabaseConfig] = None,
) -> DatabaseClient:
    """
    Setup a test database with all required tables.

    Args:
        db_config: Optional database config. If None, uses environment variables.

    Returns:
        DatabaseClient instance ready for use
    """
    if db_config is None:
        import os

        db_config = DatabaseConfig(
            username=os.getenv('DB_USERNAME'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            db_name=os.getenv('DB_NAME'),
        )

    db_client = DatabaseClient(db_config)
    await db_client.connect()
    await ensure_tables_exist(db_client)

    return db_client


async def cleanup_test_database(db_client: DatabaseClient) -> None:
    """
    Clean up test database by dropping IKB tables.

    Args:
        db_client: DatabaseClient instance
    """
    async with db_client._engine.begin() as connection:
        # Drop tables in reverse order (due to foreign key constraints)
        tables_to_drop = [
            'sift_features',
            'reference_image_features',
            'image_knowledge_bases',
        ]

        for table in tables_to_drop:
            await connection.execute(text(f'DROP TABLE IF EXISTS {table} CASCADE;'))

    await db_client.close()


async def verify_tables_exist(db_client: DatabaseClient) -> None:
    """
    Verify that all required tables exist and have the correct columns.

    Args:
        db_client: DatabaseClient instance
    """
    async with db_client._engine.begin() as connection:
        # Check if tables exist
        result = await connection.execute(
            text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('image_knowledge_bases', 'reference_image_features', 'sift_features')
            ORDER BY table_name;
        """)
        )

        tables = [row[0] for row in result.fetchall()]
        print(f'Found tables: {tables}')

        # Check if reference_image_features has ikb_id column
        if 'reference_image_features' in tables:
            result = await connection.execute(
                text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'reference_image_features'
                AND column_name = 'ikb_id';
            """)
            )

            ikb_id_column = result.fetchone()
            if ikb_id_column:
                print('✅ reference_image_features table has ikb_id column')
            else:
                print('❌ reference_image_features table missing ikb_id column')
