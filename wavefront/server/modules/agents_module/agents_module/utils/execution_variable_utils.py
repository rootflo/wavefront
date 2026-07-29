"""Workflow variables contributed by the platform itself.

Callers pass their own domain variables through `variables` untouched; this
module adds the one value wavefront owns — the id of the run — so a node inside
a workflow can stamp its outputs with the execution that produced them.

`variables` is the only channel that reaches a node: the inference service is
never handed the execution id, and threading a new parameter through
`perform_inference` -> `arium.run` -> the node protocol would be far more
invasive for the same result.

Kept deliberately small and use-case agnostic. Wavefront is middleware for any
use case, so it must not know about, mint or default a caller's domain keys — it
contributes only its own identifier here.
"""

from typing import Any, Dict, Optional
from uuid import UUID

#: Variable name carrying this run's execution id.
#:
#: Prefixed because the injection applies to *every* workflow on the server and
#: `variables` is user-facing — agent prompts resolve `{var}` from it — so a bare
#: `execution_id` could collide with a caller's own variable of that name and
#: silently change an existing workflow's behaviour.
EXECUTION_ID_VARIABLE = '_wf_execution_id'


def with_execution_variables(
    variables: Optional[Dict[str, Any]],
    execution_id: UUID | str,
) -> Dict[str, Any]:
    """Return ``variables`` plus this run's execution id.

    The injected entry is applied last so a caller cannot override it.
    """
    return {**(variables or {}), EXECUTION_ID_VARIABLE: str(execution_id)}
