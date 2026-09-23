"""Unit tests for auth plugin OAuth flow helpers and client redirects."""

import json
from unittest.mock import MagicMock

from user_management_module.controllers.auth_plugin_controller import (
    _client_redirect,
    _consume_oauth_flow,
    _store_oauth_flow,
    _OAUTH_FLOW_KEY_PREFIX,
)


def test_store_and_consume_oauth_flow_is_single_use():
    store = {}

    cache = MagicMock()

    def add(key, value, expiry=None, nx=False):
        if nx and key in store:
            return False
        store[key] = value
        return True

    cache.add.side_effect = add
    cache.get_str.side_effect = lambda key: store.get(key)
    cache.remove.side_effect = lambda key: store.pop(key, None)

    state, nonce = _store_oauth_flow(cache, 'auth-123')
    assert state and nonce
    assert f'{_OAUTH_FLOW_KEY_PREFIX}{state}' in store

    flow = _consume_oauth_flow(cache, state)
    assert flow == {'auth_id': 'auth-123', 'nonce': nonce}
    assert f'{_OAUTH_FLOW_KEY_PREFIX}{state}' not in store

    # Replay after consume must miss.
    assert _consume_oauth_flow(cache, state) is None


def test_consume_oauth_flow_missing_state_returns_none():
    cache = MagicMock()
    cache.get_str.return_value = None
    assert _consume_oauth_flow(cache, None) is None
    assert _consume_oauth_flow(cache, 'missing') is None


def test_consume_oauth_flow_rejects_corrupt_json():
    cache = MagicMock()
    cache.get_str.return_value = 'not-json'
    assert _consume_oauth_flow(cache, 'state') is None
    cache.remove.assert_called_once()


def test_consume_oauth_flow_rejects_payload_without_auth_id():
    cache = MagicMock()
    cache.get_str.return_value = json.dumps({'nonce': 'n'})
    assert _consume_oauth_flow(cache, 'state') is None


def test_client_redirect_blocks_empty_url():
    response = _client_redirect(None, 'https://app.example.com', {'token': 't'})
    assert response.headers['location'] == 'about:blank'


def test_client_redirect_blocks_unset_web_url():
    response = _client_redirect('https://app.example.com/cb', '', {'token': 't'})
    assert response.headers['location'] == 'about:blank'


def test_client_redirect_blocks_foreign_host():
    response = _client_redirect(
        'https://evil.example.com/cb',
        'https://app.example.com',
        {'token': 't'},
    )
    assert response.headers['location'] == 'about:blank'


def test_client_redirect_allows_matching_origin():
    response = _client_redirect(
        'https://app.example.com/cb',
        'https://app.example.com',
        {'access_token': 'abc'},
    )
    location = response.headers['location']
    assert location.startswith('https://app.example.com/cb?')
    assert 'access_token=abc' in location


def test_client_redirect_appends_with_ampersand_when_query_exists():
    response = _client_redirect(
        'https://app.example.com/cb?x=1',
        'https://app.example.com',
        {'y': '2'},
    )
    assert 'x=1&y=2' in response.headers['location']
