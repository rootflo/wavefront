"""
Recursive resolution of agent and subworkflow references inside an arium config.

A workflow YAML can reference other agents (via ``arium.agents[].name`` containing
a ``/``) and other workflows (via ``arium.ariums[].name`` containing a ``/`` with no
inline body). Historically these were only resolved at the top level of the arium.
These helpers resolve them at **every** nesting depth, so a reference that lives
inside a nested inline arium (e.g. the sub-workflow executed by a ForEach node) is
resolved too.

Both WorkflowCrudService (validation) and WorkflowInferenceService (runtime) use
these, passing their own YAML-fetch callable.
"""

from typing import Awaitable, Callable, List

import yaml

from agents_module.utils.version_reference_utils import parse_versioned_reference


# Keys whose presence on an ``ariums[]`` entry means it is an inline definition
# rather than a bare ``namespace/name`` reference. Mirrors the historical check.
_INLINE_ARIUM_KEYS = ('agents', 'workflow', 'function_nodes', 'yaml_file')


def _is_subworkflow_reference(arium_def: dict) -> bool:
    """A subworkflow reference is a namespaced name with no inline body."""
    name = arium_def.get('name', '')
    if '/' not in name:
        return False
    return all(arium_def.get(key) is None for key in _INLINE_ARIUM_KEYS)


async def inline_subworkflow_references(
    arium_config: dict,
    fetch_workflow_yaml: Callable[..., Awaitable[str]],
    _chain: tuple = (),
) -> dict:
    """
    Return a copy of ``arium_config`` with every subworkflow reference (at any
    nesting depth) replaced by the referenced workflow's inline arium config.

    For each reference the referenced workflow's own references are inlined first
    (depth-first), so chains of references resolve fully. ``inherit_variables`` and
    ``input_filter`` from the reference site are preserved, and the node is renamed
    to its local name (last path segment, without ``@version``) to match how the
    parent workflow's edges address it.

    Args:
        arium_config: The value of the top-level ``arium:`` key (a dict).
        fetch_workflow_yaml: async ``(workflow_name, namespace, version) -> yaml_str``
            returning the referenced workflow's raw YAML.
        _chain: internal - the chain of references currently being resolved, used
            to detect cycles.

    Raises:
        ValueError: If a cyclic subworkflow reference is detected.
    """
    ariums = arium_config.get('ariums')
    if not ariums:
        return arium_config

    updated_ariums = []
    for arium_def in ariums:
        if _is_subworkflow_reference(arium_def):
            ref_name = arium_def.get('name', '')
            if ref_name in _chain:
                cycle = ' -> '.join(_chain + (ref_name,))
                raise ValueError(f'Cyclic subworkflow reference detected: {cycle}')

            namespace, rest = ref_name.split('/', 1)
            workflow_name, version = parse_versioned_reference(rest)

            sub_yaml = await fetch_workflow_yaml(workflow_name, namespace, version)
            sub_arium = (yaml.safe_load(sub_yaml) or {}).get('arium', {}) or {}

            # Resolve references inside the referenced workflow before splicing.
            sub_arium = await inline_subworkflow_references(
                sub_arium, fetch_workflow_yaml, _chain + (ref_name,)
            )

            inline_config = dict(sub_arium)

            # Preserve reference-site overrides.
            if 'inherit_variables' in arium_def:
                inline_config['inherit_variables'] = arium_def['inherit_variables']
            if 'input_filter' in arium_def:
                inline_config['input_filter'] = arium_def['input_filter']

            # Rename to the local name (parent edges address it that way).
            local_name, _ = parse_versioned_reference(ref_name.split('/')[-1])
            inline_config['name'] = local_name

            updated_ariums.append(inline_config)
        else:
            # Inline (nested) arium definition - recurse into its own ariums.
            updated_ariums.append(
                await inline_subworkflow_references(
                    dict(arium_def), fetch_workflow_yaml, _chain
                )
            )

    result = dict(arium_config)
    result['ariums'] = updated_ariums
    return result


def extract_agent_references(arium_config: dict) -> List[str]:
    """
    Return the ordered, de-duplicated list of agent references (``namespace/name``,
    optionally ``@version``) found at any nesting depth in ``arium_config``.

    Walks ``arium.agents`` plus every nested ``arium.ariums[].agents`` recursively.
    Intended to run *after* :func:`inline_subworkflow_references`, so nested agent
    references brought in by inlined subworkflows are picked up too.
    """
    references: List[str] = []
    seen = set()

    def _walk(config: dict) -> None:
        for agent_def in config.get('agents', []) or []:
            name = agent_def.get('name', '')
            if '/' in name and name not in seen:
                seen.add(name)
                references.append(name)
        for nested in config.get('ariums', []) or []:
            _walk(nested)

    _walk(arium_config)
    return references
