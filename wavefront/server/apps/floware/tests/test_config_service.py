from unittest.mock import AsyncMock, MagicMock

from floware.services.config_service import ConfigService


def _service(datasources, knowledge_bases):
    app_config_repository = MagicMock()
    app_config_repository.get = AsyncMock(
        return_value={'app_icon': 'icon.png', 'app_config': {'theme': 'dark'}}
    )
    datasource_repository = MagicMock()
    datasource_repository.get_all = AsyncMock(return_value=datasources)
    knowledge_base_repository = MagicMock()
    knowledge_base_repository.get_all = AsyncMock(return_value=knowledge_bases)
    cloud_storage_manager = MagicMock()
    cloud_storage_manager.generate_presigned_url.return_value = 'https://signed'
    return ConfigService(
        app_config_repository=app_config_repository,
        datasource_repository=datasource_repository,
        knowledge_base_repository=knowledge_base_repository,
        cloud_storage_manager=cloud_storage_manager,
        config={
            'storage': {
                'application_bucket': 'bucket',
                'config_file_name': 'icon.png',
            }
        },
    )


async def test_settings_config_hides_backend_details():
    datasource = {
        'id': 'ds-1',
        'name': 'Sales',
        'description': 'Sales data',
        'type': 'postgres',
        'meta': {'host': 'db.internal'},
        'created_at': '2026-01-01T00:00:00',
        'updated_at': '2026-01-02T00:00:00',
    }
    knowledge_base = {
        'id': 'kb-1',
        'name': 'Docs',
        'description': 'Product docs',
        'type': 'text',
        'vector_size': 1024,
        'vector_size_1': None,
        'created_at': '2026-01-01T00:00:00',
        'updated_at': '2026-01-02T00:00:00',
    }

    settings = await _service([datasource], [knowledge_base]).get_settings_config()

    assert settings['datasources'] == [
        {
            'id': 'ds-1',
            'name': 'Sales',
            'description': 'Sales data',
            'created_at': '2026-01-01T00:00:00',
            'updated_at': '2026-01-02T00:00:00',
        }
    ]
    assert settings['knowledgebases'] == [
        {
            'id': 'kb-1',
            'name': 'Docs',
            'description': 'Product docs',
            'type': 'text',
            'created_at': '2026-01-01T00:00:00',
            'updated_at': '2026-01-02T00:00:00',
        }
    ]
    assert settings['app_icon'] == 'https://signed'
    assert settings['app_config'] == {'theme': 'dark'}


async def test_settings_config_with_no_resources():
    settings = await _service([], []).get_settings_config()

    assert settings['datasources'] == []
    assert settings['knowledgebases'] == []
