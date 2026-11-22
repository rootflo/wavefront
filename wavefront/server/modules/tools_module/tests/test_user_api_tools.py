"""floware_list_users: group filter, paging, and error reporting."""

import json

import flo_lib.http as httpx
import pytest

from tools_module.floware_api import FlowareApiClient
from tools_module.registry.function_registry import build_function_registry
from tools_module.users import user_api_tools
from tools_module.users.user_api_tools import floware_list_users


@pytest.fixture
def http(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        reply = staticmethod(lambda request: httpx.Response(200, json={}))

    def dispatch(request: httpx.Request) -> httpx.Response:
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.reply(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


API = FlowareApiClient('http://f', passthrough_secret='s3cret')
ALICE = {
    'id': 'u1',
    'email': 'a@x.ai',
    'first_name': 'A',
    'last_name': 'L',
    'username': 'al',
    'roles': [{'id': 'r'}],
    'groups': [{'id': 'g'}],
}
SLIM_ALICE = {
    'id': 'u1',
    'email': 'a@x.ai',
    'first_name': 'A',
    'last_name': 'L',
    'username': 'al',
}


def ok(data):
    return httpx.Response(200, json={'meta': {'status': 'success'}, 'data': data})


def test_registered():
    assert 'floware_list_users' in build_function_registry(API)


async def test_group_name_resolves_exact_match_then_lists_members(http):
    def reply(request):
        if request.url.path == '/floware/v1/groups':
            return ok(
                {
                    'groups': [
                        {'id': 'g-other', 'name': 'Active Old'},
                        {'id': 'g-act', 'name': 'Active'},
                    ]
                }
            )
        assert request.url.path == '/floware/v1/groups/g-act'
        return ok({'group': {'id': 'g-act', 'users': [ALICE]}})

    http.reply = staticmethod(reply)
    result = json.loads(await floware_list_users(API, group_name='Active'))

    assert result == {'users': [SLIM_ALICE]}
    assert http.requests[0].url.params['search'] == 'Active'
    assert all(r.headers['X-Passthrough'] == 's3cret' for r in http.requests)


async def test_unknown_group_name_is_empty_not_error(http):
    http.reply = staticmethod(lambda r: ok({'groups': [{'id': 'g', 'name': 'active'}]}))

    assert json.loads(await floware_list_users(API, group_name='Active')) == {
        'users': []
    }
    assert len(http.requests) == 1


async def test_missing_group_id_is_empty(http):
    http.reply = staticmethod(lambda r: httpx.Response(404, json={}))

    result = await floware_list_users(API, group_id='g-x')

    assert json.loads(result) == {'users': []}
    assert [r.url.path for r in http.requests] == ['/floware/v1/groups/g-x']


BOB = {**ALICE, 'id': 'u2', 'email': 'b@x.ai'}
CARL = {**ALICE, 'id': 'u3', 'email': 'c@x.ai'}
GROUPS = {'Active': ('g1', [ALICE, BOB]), 'Senior': ('g2', [BOB, CARL])}


def multi_reply(request):
    path = request.url.path
    if path == '/floware/v1/groups':
        name = request.url.params['search']
        hit = [{'id': GROUPS[name][0], 'name': name}] if name in GROUPS else []
        return ok({'groups': hit})
    gid = path.rsplit('/', 1)[1]
    for g_id, members in GROUPS.values():
        if g_id == gid:
            return ok({'group': {'id': gid, 'users': members}})
    return httpx.Response(404, json={})


def ids(result):
    return [u['id'] for u in json.loads(result)['users']]


async def test_multiple_names_any_is_union_without_duplicates(http):
    http.reply = staticmethod(multi_reply)

    assert ids(await floware_list_users(API, group_name='Active, Senior')) == [
        'u1',
        'u2',
        'u3',
    ]


async def test_list_input_and_all_is_intersection(http):
    http.reply = staticmethod(multi_reply)

    result = await floware_list_users(API, group_name=['Active', 'Senior'], match='all')

    assert ids(result) == ['u2']


async def test_names_and_ids_combine(http):
    http.reply = staticmethod(multi_reply)

    result = await floware_list_users(API, group_name='Active', group_id='g2')

    assert sorted(ids(result)) == ['u1', 'u2', 'u3']


async def test_any_skips_unknown_but_all_returns_empty(http):
    http.reply = staticmethod(multi_reply)

    assert ids(await floware_list_users(API, group_name='Active,Nope')) == ['u1', 'u2']
    assert (
        ids(await floware_list_users(API, group_name='Active,Nope', match='all')) == []
    )


async def test_invalid_match(http):
    assert await floware_list_users(API, group_name='Active', match='some') == (
        "Invalid match 'some': use 'any' or 'all'"
    )
    assert http.requests == []


async def test_no_group_pages_through_users(http, monkeypatch):
    monkeypatch.setattr(user_api_tools, 'PAGE_SIZE', 2)
    pages = {0: [ALICE, ALICE], 2: [ALICE]}
    http.reply = staticmethod(
        lambda r: ok({'users': pages[int(r.url.params['offset'])]})
    )

    result = json.loads(await floware_list_users(API, search='a'))

    assert len(result['users']) == 3
    assert [r.url.params['offset'] for r in http.requests] == ['0', '2']
    assert http.requests[0].url.params['search'] == 'a'


async def test_error_quotes_server_message(http):
    http.reply = staticmethod(
        lambda r: httpx.Response(
            401, json={'meta': {'status': 'failure', 'error': 'Access denied'}}
        )
    )

    assert await floware_list_users(API) == 'User list failed (401): Access denied'


async def test_role_only_sends_repeated_roles_param(http):
    http.reply = staticmethod(lambda r: ok({'users': [ALICE]}))

    result = await floware_list_users(API, role='admin, underwriter', search='a')

    assert ids(result) == ['u1']
    assert http.requests[0].url.params.get_list('roles') == ['admin', 'underwriter']
    assert http.requests[0].url.params['search'] == 'a'


async def test_role_with_groups_intersects(http):
    def reply(request):
        if request.url.path == '/floware/v1/users':
            assert request.url.params.get_list('roles') == ['admin']
            assert 'search' not in request.url.params
            return ok({'users': [BOB, CARL]})
        return multi_reply(request)

    http.reply = staticmethod(reply)

    assert ids(await floware_list_users(API, group_name='Active', role='admin')) == [
        'u2'
    ]


async def test_role_skipped_when_groups_already_empty(http):
    http.reply = staticmethod(multi_reply)

    assert ids(await floware_list_users(API, group_name='Nope', role='admin')) == []
    assert all(r.url.path != '/floware/v1/users' for r in http.requests)


async def test_group_lookup_pages_past_partial_matches(http, monkeypatch):
    monkeypatch.setattr(user_api_tools, 'GROUP_PAGE_SIZE', 2)

    def reply(request):
        if request.url.path == '/floware/v1/groups':
            pages = {
                0: [
                    {'id': 'x1', 'name': 'Inactive A'},
                    {'id': 'x2', 'name': 'Inactive B'},
                ],
                2: [{'id': 'g1', 'name': 'Active'}],
            }
            return ok({'groups': pages[int(request.url.params['offset'])]})
        return ok({'group': {'id': 'g1', 'users': [ALICE]}})

    http.reply = staticmethod(reply)

    assert ids(await floware_list_users(API, group_name='Active')) == ['u1']


async def test_bad_body_quotes_the_failing_response(http):
    def reply(request):
        if request.url.path == '/floware/v1/users':
            return httpx.Response(200, text='<html>proxy error</html>')
        return multi_reply(request)

    http.reply = staticmethod(reply)

    result = await floware_list_users(API, group_name='Active', role='admin')

    assert (
        result == 'Unexpected response from floware user API: <html>proxy error</html>'
    )


@pytest.mark.parametrize(
    'path, body',
    [
        ('/floware/v1/groups/g-x', {'group': 'not-a-dict'}),
        ('/floware/v1/groups/g-x', {'group': {'users': ['u1']}}),
        ('/floware/v1/groups/g-x', {'group': {'users': {'id': 'u1'}}}),
    ],
)
async def test_malformed_group_shapes_return_error_string(http, path, body):
    http.reply = staticmethod(lambda r: ok(body))

    result = await floware_list_users(API, group_id='g-x')

    assert result.startswith('Unexpected response from floware user API:')


async def test_malformed_user_entries_return_error_string(http):
    http.reply = staticmethod(lambda r: ok({'users': [ALICE, 'oops']}))

    result = await floware_list_users(API)

    assert result.startswith('Unexpected response from floware user API:')


async def test_malformed_groups_list_returns_error_string(http):
    http.reply = staticmethod(lambda r: ok({'groups': 'nope'}))

    result = await floware_list_users(API, group_name='Active')

    assert result.startswith('Unexpected response from floware user API:')


async def test_page_cap_is_an_error_not_a_partial_list(http, monkeypatch):
    monkeypatch.setattr(user_api_tools, 'PAGE_SIZE', 1)
    monkeypatch.setattr(user_api_tools, 'MAX_PAGES', 2)
    http.reply = staticmethod(lambda r: ok({'users': [ALICE]}))  # always a full page

    result = await floware_list_users(API)

    assert result.startswith('Too many results: the user listing exceeded 2 pages')
    assert len(http.requests) == 2


async def test_group_search_cap_is_an_error(http, monkeypatch):
    monkeypatch.setattr(user_api_tools, 'GROUP_PAGE_SIZE', 1)
    monkeypatch.setattr(user_api_tools, 'MAX_PAGES', 2)
    http.reply = staticmethod(
        lambda r: ok({'groups': [{'id': 'x', 'name': 'Inactive'}]})
    )

    result = await floware_list_users(API, group_name='Active')

    assert result.startswith(
        "Too many results: the group search for 'Active' exceeded 2 pages"
    )
