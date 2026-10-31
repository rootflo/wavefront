"""`${secrets.NAME}` helpers on the parsed YAML document and on parsed definitions."""

import pytest

from api_services_module.models.service import (
    ApiConfig,
    AuthConfig,
    AuthType,
    HttpMethod,
    ServiceDefinition,
)
from api_services_module.secrets.references import (
    find_definition_refs,
    find_literal_secrets,
    find_refs,
    find_service_refs,
    is_sensitive_header,
    mask_definition,
    replace_literals_with_refs,
    restore_masked_secrets,
    substitute,
    substitute_definition,
)
from common_module.security.secret_cipher import SECRET_MASK


def _document():
    return {
        'service': {
            'id': 'acme',
            'base_url': 'https://acme.test/{tenant}',
            'auth': {
                'id': 'acme-auth',
                'type': 'bearer',
                'token': '${secrets.ACME_TOKEN}',
                'additional_headers': {
                    'X-Partner-Key': 'literal-partner-key',
                    'X-Client-Id': 'client-1',
                    'Authorization': 'Bearer ${secrets.ACME_BEARER}',
                },
            },
            'apis': [
                {
                    'id': 'get-user',
                    'path': '/users/{id}',
                    'backend_path': '/users/{id}',
                    'additional_headers': {
                        'Cookie': 'session=abc',
                        'X-Trace': '${secrets.TRACE_ID}',
                    },
                },
                {'id': 'no-headers', 'path': '/x', 'backend_path': '/x'},
            ],
        }
    }


# ---- strings -----------------------------------------------------------------


def test_find_refs_in_strings_and_nested_values():
    assert find_refs('${secrets.A}') == {'A'}
    assert find_refs('Bearer ${secrets.TOKEN_1} and ${secrets.B}') == {'TOKEN_1', 'B'}
    assert find_refs({'x': ['${secrets.C}', {'y': '${secrets.D}'}]}) == {'C', 'D'}


def test_find_refs_ignores_path_params_and_invalid_names():
    assert find_refs('/users/{id}') == set()
    assert find_refs('${secrets.lower}') == set()
    assert find_refs('{secrets.A}') == set()
    assert find_refs(None) == set()
    assert find_refs(42) == set()


def test_substitute_whole_and_embedded_references():
    resolved = {'A': 'alpha', 'B': 'beta'}

    assert substitute('${secrets.A}', resolved) == 'alpha'
    assert (
        substitute('Bearer ${secrets.A}-${secrets.B}', resolved) == 'Bearer alpha-beta'
    )
    assert substitute({'h': ['${secrets.B}']}, resolved) == {'h': ['beta']}
    assert substitute('/users/{id}', resolved) == '/users/{id}'


def test_substitute_unknown_reference_raises():
    with pytest.raises(ValueError, match='Unknown secret: MISSING'):
        substitute('${secrets.MISSING}', {})


@pytest.mark.parametrize(
    'name',
    [
        'Authorization',
        'x-api-key',
        'X-Auth-Token',
        'Client-Secret',
        'Cookie',
        'X-PASSWORD',
    ],
)
def test_sensitive_headers(name):
    assert is_sensitive_header(name)


@pytest.mark.parametrize('name', ['X-Client-Id', 'Content-Type', 'Accept', ''])
def test_non_sensitive_headers(name):
    assert not is_sensitive_header(name)


# ---- YAML document -------------------------------------------------------------


def test_find_service_refs_only_where_references_are_honoured():
    document = _document()
    document['service']['base_url'] = 'https://${secrets.IGNORED}.test'

    assert find_service_refs(document) == {'ACME_TOKEN', 'ACME_BEARER', 'TRACE_ID'}


def test_find_literal_secrets_lists_secret_fields_and_sensitive_headers():
    document = _document()
    document['service']['auth']['password'] = 'hunter2'

    assert find_literal_secrets(document) == [
        ('service.auth.password', 'hunter2'),
        ('service.auth.additional_headers.X-Partner-Key', 'literal-partner-key'),
        ('service.apis[0].additional_headers.Cookie', 'session=abc'),
    ]


def test_find_literal_secrets_skips_references_and_empty_values():
    document = {
        'service': {
            'auth': {
                'token': 'Bearer ${secrets.T}',
                'api_key': '',
                'password': None,
                'additional_headers': {'Authorization': '${secrets.A}'},
            }
        }
    }

    assert find_literal_secrets(document) == []


def test_find_literal_secrets_accepts_the_service_mapping():
    service = _document()['service']

    paths = [path for path, _ in find_literal_secrets(service)]
    assert paths[0] == 'auth.additional_headers.X-Partner-Key'


def test_replace_literals_with_refs_returns_a_rewritten_copy():
    document = _document()
    mapping = {
        'service.auth.additional_headers.X-Partner-Key': 'ACME_PARTNER_KEY',
        'service.apis[0].additional_headers.Cookie': 'ACME_COOKIE',
        'service.auth.not_there': 'IGNORED',
    }

    rewritten = replace_literals_with_refs(document, mapping)

    headers = rewritten['service']['auth']['additional_headers']
    assert headers['X-Partner-Key'] == '${secrets.ACME_PARTNER_KEY}'
    assert headers['X-Client-Id'] == 'client-1'
    api_headers = rewritten['service']['apis'][0]['additional_headers']
    assert api_headers['Cookie'] == '${secrets.ACME_COOKIE}'
    assert find_literal_secrets(rewritten) == []
    # the input is untouched
    assert (
        document['service']['apis'][0]['additional_headers']['Cookie'] == 'session=abc'
    )


def test_restore_masked_secrets_keeps_stored_values():
    stored = _document()
    incoming = _document()
    incoming['service']['auth']['additional_headers']['X-Partner-Key'] = SECRET_MASK

    merged, unmatched = restore_masked_secrets(incoming, stored)

    assert unmatched == []
    assert (
        merged['service']['auth']['additional_headers']['X-Partner-Key']
        == 'literal-partner-key'
    )


def _two_apis(*apis):
    return {
        'service': {
            'id': 'acme',
            'auth': {'id': 'a', 'type': 'bearer', 'token': '${secrets.ACME_TOKEN}'},
            'apis': [
                {
                    'id': api_id,
                    'path': f'/{api_id}',
                    'additional_headers': {'Authorization': token},
                }
                for api_id, token in apis
            ],
        }
    }


def test_restore_masked_secrets_matches_api_headers_by_api_id():
    stored = _two_apis(('a', 'token-a'), ('b', 'token-b'))
    # API "a" was deleted, so "b" moved to index 0 and came back masked.
    incoming = _two_apis(('b', SECRET_MASK))

    merged, unmatched = restore_masked_secrets(incoming, stored)

    assert unmatched == []
    assert merged['service']['apis'][0]['additional_headers'] == {
        'Authorization': 'token-b'
    }


def test_restore_masked_secrets_survives_reordered_apis():
    stored = _two_apis(('a', 'token-a'), ('b', 'token-b'))
    incoming = _two_apis(('b', SECRET_MASK), ('a', SECRET_MASK))

    merged, _unmatched = restore_masked_secrets(incoming, stored)

    headers = [api['additional_headers'] for api in merged['service']['apis']]
    assert headers == [{'Authorization': 'token-b'}, {'Authorization': 'token-a'}]


def test_restore_masked_secrets_never_matches_ambiguous_api_ids():
    stored = _two_apis(('a', 'token-a'), ('a', 'token-other'))
    incoming = _two_apis(('a', SECRET_MASK))

    _merged, unmatched = restore_masked_secrets(incoming, stored)

    assert unmatched == ['service.apis[0].additional_headers.Authorization']


def test_restore_masked_secrets_reports_masks_without_stored_value():
    incoming = _document()
    incoming['service']['auth']['password'] = SECRET_MASK

    _merged, unmatched = restore_masked_secrets(incoming, None)

    assert unmatched == ['service.auth.password']


# ---- parsed definitions ------------------------------------------------------------


def _definition():
    return ServiceDefinition(
        id='acme',
        base_url='https://acme.test',
        auth=AuthConfig(
            id='acme-auth',
            type=AuthType.BEARER,
            token='${secrets.ACME_TOKEN}',
            additional_headers={
                'X-Partner-Key': 'literal-partner-key',
                'X-Client-Id': 'client-1',
            },
        ),
        apis=[
            ApiConfig(
                id='get-user',
                path='/users/{id}',
                backend_path='/users/{id}',
                method=HttpMethod.GET,
                additional_headers={'Authorization': 'Bearer ${secrets.API_TOKEN}'},
            )
        ],
    )


def test_definition_refs_and_substitution():
    definition = _definition()

    assert find_definition_refs(definition) == {'ACME_TOKEN', 'API_TOKEN'}

    resolved = substitute_definition(
        definition, {'ACME_TOKEN': 'tok', 'API_TOKEN': 'api'}
    )
    assert resolved.auth.token == 'tok'
    assert resolved.apis[0].additional_headers == {'Authorization': 'Bearer api'}
    assert resolved.apis[0].backend_path == '/users/{id}'
    # the stored definition keeps its references
    assert definition.auth.token == '${secrets.ACME_TOKEN}'


def test_mask_definition_masks_literals_and_keeps_references():
    definition = _definition()
    definition.auth.password = 'hunter2'

    masked = mask_definition(definition)

    assert masked.auth.token == '${secrets.ACME_TOKEN}'
    assert masked.auth.password == SECRET_MASK
    assert masked.auth.api_key is None
    assert masked.auth.additional_headers == {
        'X-Partner-Key': SECRET_MASK,
        'X-Client-Id': 'client-1',
    }
    assert masked.apis[0].additional_headers == {
        'Authorization': 'Bearer ${secrets.API_TOKEN}'
    }
    assert definition.auth.password == 'hunter2'
