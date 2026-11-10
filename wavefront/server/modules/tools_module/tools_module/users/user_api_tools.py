"""Tools that read floware's user directory via its own REST API.

Calls go out with ``api.headers()``: the passthrough secret outside
production, service-mesh identity within it. Floware treats both as a service
identity, which passes the admin gate on the user and group endpoints.
"""

import json
from urllib.parse import quote

import flo_lib.http as httpx

from tools_module.floware_api import FlowareApiClient

PAGE_SIZE = 500  # the /v1/users maximum
MAX_PAGES = 40
GROUP_PAGE_SIZE = 100
USER_FIELDS = ('id', 'email', 'first_name', 'last_name', 'username')


def _error_message(response) -> str:
    """The API's own error text, or '' if the body is not the usual envelope."""
    try:
        return response.json().get('meta', {}).get('error') or ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''


class _BadResponse(Exception):
    """A 200 whose body is not the usual {"data": {...}} envelope."""

    def __init__(self, response):
        super().__init__(response.text)
        self.text = response.text


def _data(response) -> dict:
    """The response's data object, or _BadResponse quoting THIS response's body."""
    try:
        data = response.json().get('data')
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        raise _BadResponse(response) from e
    if not isinstance(data, dict):
        raise _BadResponse(response)
    return data


def _records(response, container: dict, key: str) -> list[dict]:
    """container[key] as a list of dicts; anything else is a malformed response.

    Missing or null is an empty list. Checking the shape here keeps a bad body
    on the _BadResponse path instead of surfacing as AttributeError/TypeError.
    """
    value = container.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise _BadResponse(response)
    return value


class _TooManyPages(Exception):
    """Paging hit MAX_PAGES with results still coming: refuse a partial answer."""

    def __init__(self, what: str):
        super().__init__(what)
        self.what = what


def _slim(user: dict) -> dict:
    """Only the identity fields: no roles or groups in a model's context."""
    return {key: user.get(key) for key in USER_FIELDS}


def _failure(what: str, response) -> str:
    return f'{what} failed ({response.status_code}): {_error_message(response) or response.text}'


def _as_list(value) -> list[str]:
    """A list, or a comma-separated string, as a de-duplicated list of names/ids."""
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(',')
    seen, out = set(), []
    for item in items:
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


async def _group_members(client, api: FlowareApiClient, base: str, group_id: str):
    """(members, error). A missing group is no members, not an error."""
    response = await client.get(
        f'{base}/groups/{quote(group_id, safe="")}', headers=api.headers(), timeout=30.0
    )
    if response.status_code == 404:
        return [], None
    if response.status_code != 200:
        return None, _failure('Group fetch', response)
    group = _data(response).get('group')
    if group is None:
        return [], None
    if not isinstance(group, dict):
        raise _BadResponse(response)
    return _records(response, group, 'users'), None


async def _find_group(client, api: FlowareApiClient, base: str, name: str):
    """(group_id or None, error). Pages the search so an exact match is found
    even when many groups merely contain the name."""
    offset = 0
    for _ in range(MAX_PAGES):
        response = await client.get(
            f'{base}/groups',
            params={'search': name, 'limit': GROUP_PAGE_SIZE, 'offset': offset},
            headers=api.headers(),
            timeout=30.0,
        )
        if response.status_code != 200:
            return None, _failure('Group lookup', response)
        groups = _records(response, _data(response), 'groups')
        for group in groups:
            if group.get('name') == name and group.get('id'):
                return group['id'], None
        if len(groups) < GROUP_PAGE_SIZE:
            return None, None
        offset += GROUP_PAGE_SIZE
    raise _TooManyPages(f"group search for '{name}'")


async def _list_users(client, api: FlowareApiClient, base: str, search, roles):
    """(users, error) from the paged /v1/users listing."""
    users, offset = [], 0
    for _ in range(MAX_PAGES):
        params = {'limit': PAGE_SIZE, 'offset': offset, 'force_fetch': 1}
        if search:
            params['search'] = search
        if roles:
            params['roles'] = roles  # repeated ?roles=a&roles=b, matches any
        response = await client.get(
            f'{base}/users', params=params, headers=api.headers(), timeout=30.0
        )
        if response.status_code != 200:
            return None, _failure('User list', response)
        page = _records(response, _data(response), 'users')
        users.extend(page)
        if len(page) < PAGE_SIZE:
            return users, None
        offset += PAGE_SIZE
    raise _TooManyPages('user listing')


async def floware_list_users(
    api: FlowareApiClient,
    /,
    group_name=None,
    group_id=None,
    search: str = None,
    match: str = 'any',
    role=None,
) -> str:
    """List floware users, optionally only members of one or more groups.

    group_name / group_id: one value, a list, or a comma-separated string.
    Names must match exactly; unknown names and ids are skipped. Both may be
    given together and are combined.
    match: 'any' (default) = in at least one of the groups; 'all' = in every one.
    With 'all', an unknown group means nobody matches.
    role: one role name, a list, or a comma-separated string. Users holding
    ANY of them directly (roles inherited through a group do not count).
    Combined with groups, a user must satisfy both.
    search filters by name or email and only applies without a group.

    Returns JSON {"users": [{id, email, first_name, last_name, username}]}.
    """
    base = f'{api.base_url}/floware/v1'
    names = _as_list(group_name)
    ids = _as_list(group_id)
    roles = _as_list(role)
    match = (match or 'any').strip().lower()
    if match not in ('any', 'all'):
        return f"Invalid match '{match}': use 'any' or 'all'"

    async with httpx.AsyncClient() as client:
        try:
            if names or ids:
                missing = False
                for name in names:
                    found, error = await _find_group(client, api, base, name)
                    if error:
                        return error
                    if found:
                        if found not in ids:
                            ids.append(found)
                    else:
                        missing = True
                if match == 'all' and missing:
                    return json.dumps({'users': []})

                users_by_id: dict[str, dict] = {}
                member_sets: list[set[str]] = []
                for gid in ids:
                    members, error = await _group_members(client, api, base, gid)
                    if error:
                        return error
                    member_sets.append({u['id'] for u in members if u.get('id')})
                    for u in members:
                        if u.get('id'):
                            users_by_id.setdefault(u['id'], u)

                if not member_sets:
                    return json.dumps({'users': []})
                keep = (
                    set.intersection(*member_sets)
                    if match == 'all'
                    else set.union(*member_sets)
                )
                if roles and keep:
                    with_role, error = await _list_users(client, api, base, None, roles)
                    if error:
                        return error
                    keep &= {u.get('id') for u in with_role}
                return json.dumps(
                    {
                        'users': [
                            _slim(u) for uid, u in users_by_id.items() if uid in keep
                        ]
                    }
                )

            users, error = await _list_users(client, api, base, search, roles)
            if error:
                return error
            users = [_slim(u) for u in users]
            return json.dumps({'users': users})
        except httpx.RequestError as e:
            return f'Failed to reach floware user API: {e}'
        except _BadResponse as e:
            return f'Unexpected response from floware user API: {e.text}'
        except _TooManyPages as e:
            return (
                f'Too many results: the {e.what} exceeded {MAX_PAGES} pages. '
                'Narrow it with group_name, group_id, role or search.'
            )
