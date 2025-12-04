import pytest
import os
from pathlib import Path


from db_repo_module.database.connection import DatabaseClient, DatabaseConfig


@pytest.fixture(scope='session')
async def db_client():
    """Create database client for testing"""
    db_config = DatabaseConfig(
        username=os.getenv('DB_USERNAME', 'test_user'),
        password=os.getenv('DB_PASSWORD', 'test_password'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        db_name=os.getenv('DB_NAME', 'test_db'),
    )

    db_client = DatabaseClient(db_config)
    await db_client.connect()
    yield db_client
    await db_client.close()  # Fix: Use correct method name


@pytest.fixture
def test_image_base64():
    """Provide a test image as base64 data URL"""
    return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@pytest.fixture
def test_images_dir():
    """Provide path to test images directory"""
    return Path(__file__).parent / 'test_images'
