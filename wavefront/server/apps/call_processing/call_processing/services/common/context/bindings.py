"""Tool arguments the server fills in instead of the AI.

A tool association opts in through ``config_overrides.context.bind``, mapping
an argument to a call variable. The argument is a dotted path, so a field
nested inside an object argument can be bound too::

    "context": {"bind": {"mobile_number": "caller.phone"}}
    "context": {"bind": {"request.phone": "caller.phone"}}

Bound fields are hidden from the AI's tool schema and written into the
arguments before the tool runs. A variable with no value on this call (no
phone number on a browser call, say) leaves the field with the AI, which is
how every tool works today. So does a bind that can't apply (unknown
variable, no such field, not a text field): it is logged and ignored.
"""

import copy
from typing import Any, Dict, List, Optional

from call_processing.log.logger import logger
from call_processing.services.common.context.subject import CallSubject

CALL_VARIABLES = ('caller.phone', 'call.id', 'call.direction', 'agent.id')
# Plus outbound.<key>: a value the CRM sent with an outbound call (context)
OUTBOUND_PREFIX = 'outbound.'


def _is_call_variable(variable: Any) -> bool:
    if not isinstance(variable, str):
        return False
    if variable.startswith(OUTBOUND_PREFIX):
        return len(variable) > len(OUTBOUND_PREFIX)
    return variable in CALL_VARIABLES


def tool_context(tool: Dict[str, Any]) -> Dict[str, Any]:
    """The tool association's ``config_overrides.context`` settings ({} if none)."""
    overrides = (tool.get('association') or {}).get('config_overrides') or {}
    return overrides.get('context') or {}


def tool_prompt_fields(tool: Dict[str, Any]) -> List[str]:
    """Result fields (dotted paths) to give the AI up front, from ``prompt_fields``."""
    fields = tool_context(tool).get('prompt_fields') or []
    if not isinstance(fields, list):
        return []
    return [f for f in fields if isinstance(f, str) and f.strip()]


def _schema_field(schema: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
    """The JSON-schema of the field at a dotted path, or None if there is none."""
    node: Any = schema
    for part in path.split('.'):
        properties = node.get('properties') if isinstance(node, dict) else None
        if not isinstance(properties, dict) or part not in properties:
            return None
        node = properties[part]
    return node if isinstance(node, dict) else None


def tool_bindings(tool: Dict[str, Any]) -> Dict[str, str]:
    """The tool's usable binds: field path -> call variable.

    Every call variable is text, so only a string field can take one. Binds
    that can't apply are logged and left to the AI; the tool still loads.
    """
    bind = tool_context(tool).get('bind') or {}
    schema = tool.get('parameter_schema') or {}
    usable = {}
    for path, variable in bind.items():
        field = _schema_field(schema, path)
        if not _is_call_variable(variable):
            problem = (
                f'unknown variable {variable!r}; expected one of '
                f'{list(CALL_VARIABLES)} or {OUTBOUND_PREFIX}<key>'
            )
        elif field is None:
            problem = 'no such field in the tool schema'
        elif field.get('type') != 'string':
            problem = f"it is a {field.get('type', 'untyped')} field, not text"
        else:
            usable[path] = variable
            continue
        logger.warning(
            f"Ignoring bind '{path}' for tool '{tool.get('name')}': {problem}"
        )
    return usable


def resolve_bindings(
    bind: Dict[str, str],
    subject: Optional[CallSubject],
    agent_id: Optional[str],
    outbound: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Argument name -> value, for the variables that have a value on this call."""
    values = {'agent.id': agent_id or ''}
    for key, value in (outbound or {}).items():
        values[f'{OUTBOUND_PREFIX}{key}'] = value
    if subject is not None:
        values.update(
            {
                'caller.phone': subject.phone,
                'call.id': subject.call_ref,
                'call.direction': subject.direction,
            }
        )
    return {arg: values[var] for arg, var in bind.items() if values.get(var)}


def hidden_schema(schema: Dict[str, Any], paths) -> Dict[str, Any]:
    """A copy of the tool's schema without the bound fields (what the AI sees).

    An object left with no fields of its own is removed too.
    """
    schema = copy.deepcopy(schema)
    for path in paths:
        _remove_field(schema, path.split('.'))
    return schema


def _remove_field(node: Dict[str, Any], parts: List[str]) -> None:
    properties = node.get('properties')
    head = parts[0]
    if not isinstance(properties, dict) or head not in properties:
        return
    if len(parts) > 1:
        _remove_field(properties[head], parts[1:])
        if properties[head].get('properties'):
            return  # the object still has fields for the AI
    del properties[head]
    if head in (node.get('required') or []):
        node['required'] = [name for name in node['required'] if name != head]


def merge_bound(args: Any, values: Dict[str, str]) -> Dict[str, Any]:
    """The AI's arguments with the server's values written in (the server wins).

    Creates the enclosing object when the AI left it out.
    """
    merged = copy.deepcopy(args) if isinstance(args, dict) else {}
    for path, value in values.items():
        *parents, leaf = path.split('.')
        node = merged
        for part in parents:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[leaf] = value
    return merged


def unbound_required(schema: Dict[str, Any], bound_paths) -> List[str]:
    """Required fields the server doesn't fill, as dotted paths, at every level.

    An object is looked into when it is required or holds a bound field (it is
    sent either way); optional fields left unbound are simply not sent.
    """
    bound = set(bound_paths)
    missing: List[str] = []

    def walk(node: Dict[str, Any], prefix: str) -> None:
        required = set(node.get('required') or [])
        for name, spec in (node.get('properties') or {}).items():
            path = f'{prefix}{name}'
            if path in bound:
                continue
            holds_bound = any(p.startswith(f'{path}.') for p in bound)
            if isinstance(spec, dict) and spec.get('properties'):
                if name in required or holds_bound:
                    walk(spec, f'{path}.')
            elif name in required:
                missing.append(path)

    walk(schema, '')
    return missing
