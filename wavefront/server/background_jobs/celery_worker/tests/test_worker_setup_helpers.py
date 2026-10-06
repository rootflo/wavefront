"""Pure helpers on services wiring."""

from celery_worker.services import _build_db_client


def test_build_db_client_maps_config_fields():
    client = _build_db_client(
        {
            'username': 'u',
            'password': 'p',
            'host': 'localhost',
            'port': '5432',
            'db_name': 'floware',
            'pool_size': '5',
            'max_overflow': '2',
            'pool_timeout': '10',
            'pool_recycle': '100',
        }
    )
    cfg = client.db_config
    assert cfg.username == 'u'
    assert cfg.password == 'p'
    assert cfg.host == 'localhost'
    assert cfg.port == '5432'
    assert cfg.db_name == 'floware'
    assert cfg.pool_size == '5'
