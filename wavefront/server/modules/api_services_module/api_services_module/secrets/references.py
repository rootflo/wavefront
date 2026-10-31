"""`${secrets.NAME}` references in API service definitions.

A service YAML holds credentials only as references to rows of the `secrets`
table. References are honoured in these places, and may be embedded in a
longer string (`Bearer ${secrets.ACME_TOKEN}`):
- `service.auth.token`, `service.auth.password`, `service.auth.api_key`
- header values of `service.auth.additional_headers`
- header values of `service.apis[].additional_headers`

The dict helpers work on the parsed YAML document so the data migration can use
them without the parser; the `*_definition` helpers do the same on a parsed
`ServiceDefinition`.
"""

import copy
import dataclasses
import re
from typing import Any, Iterator, List, Mapping, MutableMapping, Optional, Set, Tuple

from common_module.security.secret_cipher import SECRET_MASK

from ..models.service import ServiceDefinition

SECRET_NAME_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')
# `$` keeps this apart from the `{param}` path templating in pipeline/stages.py.
SECRET_REF_PATTERN = re.compile(r'\$\{secrets\.([A-Z][A-Z0-9_]*)\}')
SECRET_REF_MARKER = '${secrets.'
SECRET_AUTH_FIELDS = ('token', 'password', 'api_key')
SENSITIVE_HEADER_PATTERN = re.compile(
    r'authorization|token|secret|key|cookie|password', re.IGNORECASE
)

__all__ = [
    'SECRET_AUTH_FIELDS',
    'SECRET_NAME_PATTERN',
    'SECRET_REF_PATTERN',
    'find_definition_refs',
    'find_literal_secrets',
    'find_refs',
    'find_service_refs',
    'is_literal_secret',
    'is_sensitive_header',
    'iter_secret_fields',
    'make_ref',
    'mask_definition',
    'replace_literals_with_refs',
    'restore_masked_secrets',
    'substitute',
    'substitute_definition',
]


def make_ref(name: str) -> str:
    return f'${{secrets.{name}}}'


def is_sensitive_header(name: str) -> bool:
    """True for a header whose value is a credential (by its name)."""
    return bool(name) and bool(SENSITIVE_HEADER_PATTERN.search(str(name)))


def find_refs(value: Any) -> Set[str]:
    """Names referenced anywhere in a string, or nested dicts and lists of them."""
    if isinstance(value, str):
        return set(SECRET_REF_PATTERN.findall(value))
    names: Set[str] = set()
    if isinstance(value, Mapping):
        for item in value.values():
            names |= find_refs(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            names |= find_refs(item)
    return names


def substitute(value: Any, resolved: Mapping[str, str]) -> Any:
    """Copy of `value` with every reference replaced by its resolved value.

    Raises `ValueError` for a reference missing from `resolved`.
    """
    if isinstance(value, str):

        def _replace(match: re.Match) -> str:
            name = match.group(1)
            if name not in resolved:
                raise ValueError(f'Unknown secret: {name}')
            return resolved[name]

        return SECRET_REF_PATTERN.sub(_replace, value)
    if isinstance(value, Mapping):
        return {key: substitute(item, resolved) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, resolved) for item in value]
    if isinstance(value, tuple):
        return tuple(substitute(item, resolved) for item in value)
    return value


def is_literal_secret(value: Any) -> bool:
    """A non-empty value that does not use a `${secrets.` reference."""
    if value is None or value == '':
        return False
    return SECRET_REF_MARKER not in str(value)


# ---- parsed YAML document ------------------------------------------------


def _service_root(service_yaml_dict: Mapping[str, Any]) -> Tuple[Any, str]:
    if isinstance(service_yaml_dict, Mapping) and 'service' in service_yaml_dict:
        return service_yaml_dict['service'], 'service.'
    return service_yaml_dict, ''


def iter_secret_fields(
    service_yaml_dict: Mapping[str, Any],
) -> Iterator[Tuple[str, MutableMapping[str, Any], str, bool]]:
    """Yield `(path, parent, key, sensitive)` for each place a reference is honoured.

    `sensitive` is False for a header whose name does not mark it as a
    credential: it may still hold a reference but a literal there is fine.
    Accepts the whole document (`{'service': ...}`) or the service mapping.
    """
    service, prefix = _service_root(service_yaml_dict)
    if not isinstance(service, Mapping):
        return

    auth = service.get('auth')
    if isinstance(auth, Mapping):
        for field in SECRET_AUTH_FIELDS:
            if field in auth:
                yield f'{prefix}auth.{field}', auth, field, True
        headers = auth.get('additional_headers')
        if isinstance(headers, Mapping):
            for name in list(headers):
                yield (
                    f'{prefix}auth.additional_headers.{name}',
                    headers,
                    name,
                    is_sensitive_header(name),
                )

    apis = service.get('apis')
    if isinstance(apis, list):
        for index, api in enumerate(apis):
            if not isinstance(api, Mapping):
                continue
            headers = api.get('additional_headers')
            if isinstance(headers, Mapping):
                for name in list(headers):
                    yield (
                        f'{prefix}apis[{index}].additional_headers.{name}',
                        headers,
                        name,
                        is_sensitive_header(name),
                    )


def find_service_refs(service_yaml_dict: Mapping[str, Any]) -> Set[str]:
    """Secret names referenced where references are honoured."""
    names: Set[str] = set()
    for _path, parent, key, _sensitive in iter_secret_fields(service_yaml_dict):
        names |= find_refs(parent[key])
    return names


def find_literal_secrets(service_yaml_dict: Mapping[str, Any]) -> List[Tuple[str, Any]]:
    """`(path, value)` for each secret field or sensitive header holding a literal."""
    return [
        (path, parent[key])
        for path, parent, key, sensitive in iter_secret_fields(service_yaml_dict)
        if sensitive and is_literal_secret(parent[key])
    ]


def replace_literals_with_refs(
    service_yaml_dict: Mapping[str, Any], mapping: Mapping[str, str]
) -> dict:
    """Copy of the document with the value at each path replaced by `${secrets.NAME}`.

    `mapping` is `{path: secret_name}`, with paths as `find_literal_secrets`
    returns them. Paths not present in the document are ignored.
    """
    result = copy.deepcopy(dict(service_yaml_dict))
    for path, parent, key, _sensitive in iter_secret_fields(result):
        name = mapping.get(path)
        if name is not None:
            parent[key] = make_ref(name)
    return result


def restore_masked_secrets(
    service_yaml_dict: Mapping[str, Any], stored_yaml_dict: Optional[Mapping[str, Any]]
) -> Tuple[dict, List[str]]:
    """Put stored values back where an edit sent a secret field back masked.

    Read paths mask literal secrets, so an edit built from them carries
    `SECRET_MASK` for a value it did not change. Returns the merged copy and the
    paths that were masked but have no stored value.
    """
    stored: dict = {}
    duplicates: Set[str] = set()
    for identity, _path, parent, key in _iter_by_identity(stored_yaml_dict or {}):
        if identity in stored:
            duplicates.add(identity)
        stored[identity] = parent[key]
    for identity in duplicates:
        del stored[identity]

    result = copy.deepcopy(dict(service_yaml_dict))
    missing: List[str] = []
    for identity, path, parent, key in _iter_by_identity(result):
        if parent[key] != SECRET_MASK:
            continue
        if identity in stored and stored[identity] != SECRET_MASK:
            parent[key] = stored[identity]
        else:
            missing.append(path)
    return result, missing


_API_HEADER_PATH = re.compile(r'^(?:service\.)?apis\[(\d+)\]\.(.+)$')


def _iter_by_identity(
    service_yaml_dict: Mapping[str, Any],
) -> Iterator[Tuple[Optional[str], str, MutableMapping[str, Any], str]]:
    """Like `iter_secret_fields`, keyed so a field matches across edits.

    API headers are keyed by the API's `id`, not its position: an edit that
    adds, removes or reorders APIs must never pair one API's masked header with
    another API's stored value. An API without an id gets no identity.
    """
    service, _prefix = _service_root(service_yaml_dict)
    apis = service.get('apis') if isinstance(service, Mapping) else None
    for path, parent, key, _sensitive in iter_secret_fields(service_yaml_dict):
        match = _API_HEADER_PATH.match(path)
        if not match:
            yield path.removeprefix('service.'), path, parent, key
            continue
        api = apis[int(match.group(1))] if isinstance(apis, list) else None
        api_id = api.get('id') if isinstance(api, Mapping) else None
        identity = f'apis[id={api_id}].{match.group(2)}' if api_id else None
        yield identity, path, parent, key


# ---- parsed ServiceDefinition ---------------------------------------------


def find_definition_refs(definition: ServiceDefinition) -> Set[str]:
    """Secret names a parsed service references where references are honoured."""
    auth = definition.auth
    values: List[Any] = [getattr(auth, field) for field in SECRET_AUTH_FIELDS]
    values.append(auth.additional_headers or {})
    values.extend(api.additional_headers or {} for api in definition.apis)
    return find_refs(values)


def substitute_definition(
    definition: ServiceDefinition, resolved: Mapping[str, str]
) -> ServiceDefinition:
    """Execution copy of `definition` with its references resolved."""
    auth = definition.auth
    auth_changes = {
        field: substitute(getattr(auth, field), resolved)
        for field in SECRET_AUTH_FIELDS
    }
    auth_changes['additional_headers'] = substitute(
        dict(auth.additional_headers or {}), resolved
    )
    apis = [
        dataclasses.replace(
            api,
            additional_headers=substitute(dict(api.additional_headers or {}), resolved),
        )
        for api in definition.apis
    ]
    return dataclasses.replace(
        definition, auth=dataclasses.replace(auth, **auth_changes), apis=apis
    )


def _mask_headers(headers: Optional[Mapping[str, Any]]) -> dict:
    return {
        name: SECRET_MASK
        if is_sensitive_header(name) and is_literal_secret(value)
        else value
        for name, value in (headers or {}).items()
    }


def mask_definition(definition: ServiceDefinition) -> ServiceDefinition:
    """Copy of an unresolved definition with every literal secret masked.

    References are kept, so a reader sees which secret a field uses.
    """
    auth = definition.auth
    auth_changes = {
        field: SECRET_MASK
        for field in SECRET_AUTH_FIELDS
        if is_literal_secret(getattr(auth, field))
    }
    auth_changes['additional_headers'] = _mask_headers(auth.additional_headers)
    apis = [
        dataclasses.replace(
            api, additional_headers=_mask_headers(api.additional_headers)
        )
        for api in definition.apis
    ]
    return dataclasses.replace(
        definition, auth=dataclasses.replace(auth, **auth_changes), apis=apis
    )
