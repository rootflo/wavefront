"""
Deterministic, field-based routing for Arium workflows.

Unlike the LLM routers in ``llm_router.py``, a field-match router makes no model
call: it reads a named field from the most recent node's JSON output and maps its
value to a target node. Useful when an upstream agent has already produced a
structured decision (e.g. a classifier emitting ``doc_type``) and you just want to
branch on it deterministically.
"""

from typing import Any, Callable, Dict, Literal, Optional

from flo_ai.utils.flo_utils import FloUtils
from flo_ai.utils.logger import logger


def create_field_match_router(
    field: str,
    routes: Dict[str, str],
    default: Optional[str] = None,
) -> Callable[..., str]:
    """
    Build a deterministic router that reads ``field`` from the most recent node's
    JSON output and returns ``routes[value]``, falling back to ``default``.

    Args:
        field: JSON key to read from the previous node's output.
        routes: Mapping of field value -> target node name.
        default: Node to route to when the value is missing/unmapped. Must be set
            unless ``routes`` already covers every possible value.

    Returns:
        A router function annotated ``-> Literal[...]`` over every reachable target
        (route values + default), so it satisfies Arium's edge validation.
    """
    # Preserve order, dedupe; the default (if any) is also a valid target.
    targets = list(
        dict.fromkeys(list(routes.values()) + ([default] if default else []))
    )
    if not targets:
        raise ValueError('field_match router must have at least one route target')

    def field_match_router(
        memory: Any, execution_context: Optional[dict] = None
    ) -> str:
        value = None
        items = memory.get() if hasattr(memory, 'get') else None
        if items:
            content = getattr(items[-1].result, 'content', items[-1].result)
            try:
                data = FloUtils.extract_jsons_from_string(str(content))
            except Exception as e:
                logger.warning(f'field_match router: could not parse JSON output: {e}')
                data = {}
            if isinstance(data, dict):
                value = data.get(field)

        # Only a string value can match a route key; a non-scalar value (list /
        # object) is even unhashable and would raise in dict.get - so treat any
        # non-string value as unmapped and fall back to default.
        target = routes.get(value, default) if isinstance(value, str) else default
        if target is None:
            raise ValueError(
                f"field_match router: value {value!r} for field '{field}' is not in "
                'routes and no default is set'
            )
        logger.info(f'field_match router: {field}={value!r} -> {target}')
        return target

    # Advertise the reachable targets as a Literal so add_edge() can validate the
    # router against the edge's `to:` set. The members come from a runtime tuple
    # (Literal[('a', 'b')] == Literal['a', 'b']), which static type checkers can't
    # verify - the value is correct at runtime, so the check is suppressed.
    field_match_router.__annotations__['return'] = Literal[tuple(targets)]  # type: ignore
    return field_match_router
