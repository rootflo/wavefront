"""Tool arguments the server fills in instead of the AI.

A tool association opts in through ``config_overrides.context.bind``, mapping
an argument name to a call variable::

    "context": {"bind": {"mobile_number": "caller.phone"}}

Bound arguments are hidden from the AI's tool schema and merged into the
arguments before the tool runs. A variable with no value on this call (no
phone number on a browser call, say) leaves the argument with the AI, which
is how every tool works today.
"""

from typing import Any, Dict, Optional

from call_processing.services.common.context.subject import CallSubject

CALL_VARIABLES = ('caller.phone', 'call.id', 'call.direction', 'agent.id')


def tool_bindings(tool: Dict[str, Any]) -> Dict[str, str]:
    """The tool's ``bind`` map; raises ``ValueError`` on an unknown variable."""
    overrides = (tool.get('association') or {}).get('config_overrides') or {}
    bind = (overrides.get('context') or {}).get('bind') or {}
    unknown = sorted(set(bind.values()) - set(CALL_VARIABLES))
    if unknown:
        raise ValueError(
            f'Unknown bind variable(s) {unknown}; '
            f'expected one of {list(CALL_VARIABLES)}'
        )
    return dict(bind)


def resolve_bindings(
    bind: Dict[str, str], subject: Optional[CallSubject], agent_id: Optional[str]
) -> Dict[str, str]:
    """Argument name -> value, for the variables that have a value on this call."""
    values = {'agent.id': agent_id or ''}
    if subject is not None:
        values.update(
            {
                'caller.phone': subject.phone,
                'call.id': subject.call_ref,
                'call.direction': subject.direction,
            }
        )
    return {arg: values[var] for arg, var in bind.items() if values.get(var)}
