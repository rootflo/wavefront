"""
Static validation of agent and workflow (arium) YAML documents.

Validation here never builds an LLM, loads a tool or touches the network. It runs
flo_ai's own pydantic models (``AgentYamlModel`` / ``AriumYamlModel``) and then the
graph rules ``AriumBuilder.from_yaml`` / ``BaseArium.add_edge`` enforce while a
workflow is built, so a document that passes is one the builder will accept, and
every problem is reported with the path of the offending key instead of the first
one as a flat string.

Anything that needs I/O - does a referenced agent or workflow exist, does a tool
exist - is only *collected* here (``ValidationReport.agent_refs`` and
``ValidationReport.tool_refs``) and resolved by the CRUD services, which own the
repositories and storage.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, NamedTuple, Optional, Tuple

import yaml
from flo_ai.models.agent import AgentConfigModel, AgentYamlModel
from flo_ai.models.arium import AriumYamlModel, RouterConfigModel
from pydantic import ValidationError

from agents_module.models.yaml_validation_schemas import YamlValidationError
from agents_module.utils.version_reference_utils import parse_versioned_reference

# Edge target that means "stop here". It is not a node: the builder skips it when
# wiring edges and rejects it as a start/end node.
END_NODE = 'end'

# Router types whose router may route back to the node the edge leaves from
# (``supports_self_reference`` on the router the builder creates).
_SELF_REFERENCING_ROUTERS = frozenset({'reflection', 'plan_execute'})

# pydantic labels the failing branch of a ``Union`` in the error location
_UNION_BRANCH_LABELS = frozenset({'str', 'int', 'float', 'bool'})


class ToolReference(NamedTuple):
    """A tool an agent asks for, to be resolved by the caller"""

    path: str
    name: str


class AgentReference(NamedTuple):
    """A stored agent a workflow points at (``namespace/name[@version]``)"""

    path: str
    reference: str


@dataclass
class ValidationReport:
    """Everything a static pass found, plus what it could not check without I/O"""

    errors: List[YamlValidationError] = field(default_factory=list)
    tool_refs: List[ToolReference] = field(default_factory=list)
    agent_refs: List[AgentReference] = field(default_factory=list)
    # False when the document did not even fit the pydantic models; the refs
    # are only trustworthy once it did
    schema_valid: bool = False

    def add(self, path: str, message: str) -> None:
        self.errors.append(YamlValidationError(path=path, message=message))


def missing_tool_error(tool_ref: ToolReference) -> YamlValidationError:
    """The error for a tool an agent names that nothing provides."""
    return YamlValidationError(
        path=tool_ref.path,
        message=(
            f"Tool '{tool_ref.name}' not found in available tools, "
            'message processors, or API services'
        ),
    )


def format_validation_errors(errors: List[YamlValidationError]) -> str:
    """Flatten errors into one message for callers that raise instead of return."""
    return '; '.join(
        f'{error.path}: {error.message}' if error.path else error.message
        for error in errors
    )


def decode_yaml_body(body: bytes) -> Tuple[Optional[str], List[YamlValidationError]]:
    """Decode a request body as UTF-8 text, reporting rather than raising."""
    try:
        return body.decode('utf-8'), []
    except UnicodeDecodeError:
        return None, [
            YamlValidationError(path='', message='Request body is not valid UTF-8')
        ]


def parse_yaml_document(
    yaml_content: str,
) -> Tuple[Optional[Dict[str, Any]], List[YamlValidationError]]:
    """
    Parse YAML safely into a mapping.

    Returns:
        (document, []) on success, or (None, [error]) when the text is empty, is not
        valid YAML, or its root is not a mapping.
    """
    if not yaml_content or not yaml_content.strip():
        return None, [YamlValidationError(path='', message='YAML is empty')]

    try:
        data = yaml.safe_load(yaml_content)
    except (yaml.YAMLError, ValueError) as e:
        mark = getattr(e, 'problem_mark', None)
        problem = getattr(e, 'problem', None) or str(e)
        message = f'Invalid YAML: {problem}'
        if mark is not None:
            message += f' (line {mark.line + 1}, column {mark.column + 1})'
        return None, [YamlValidationError(path='', message=message)]

    if not isinstance(data, dict):
        return None, [
            YamlValidationError(
                path='',
                message='YAML root must be a mapping (for example "agent:" or "arium:")',
            )
        ]
    return data, []


def _join(prefix: str, suffix: str) -> str:
    if not prefix:
        return suffix
    if not suffix:
        return prefix
    return f'{prefix}{suffix}' if suffix.startswith('[') else f'{prefix}.{suffix}'


def _loc_to_path(loc: Tuple[Any, ...], data: Any) -> str:
    """
    Turn a pydantic error location into a path such as ``arium.agents[0].model``.

    The original document is walked alongside so the branch labels pydantic puts in
    a ``Union`` location (``tools[0].ToolConfigModel.name``) can be dropped: they
    are not keys in the document.
    """
    path = ''
    current = data

    for part in loc:
        if isinstance(part, int):
            path += f'[{part}]'
            current = (
                current[part]
                if isinstance(current, list) and 0 <= part < len(current)
                else None
            )
            continue

        part = str(part)
        resolvable = isinstance(current, dict) and part in current
        is_label = part in _UNION_BRANCH_LABELS or part.endswith('Model') or '[' in part
        if not resolvable and is_label:
            continue

        path = f'{path}.{part}' if path else part
        current = current.get(part) if resolvable else None

    return path


def _pydantic_errors(
    exc: ValidationError, data: Any, prefix: str = ''
) -> List[YamlValidationError]:
    errors: List[YamlValidationError] = []
    seen = set()
    for error in exc.errors():
        path = _join(prefix, _loc_to_path(tuple(error['loc']), data))
        message = error['msg']
        if message.startswith('Value error, '):
            message = message[len('Value error, ') :]
        if (path, message) in seen:
            continue
        seen.add((path, message))
        errors.append(YamlValidationError(path=path, message=message))
    return errors


def _check_agent_config(
    config: AgentConfigModel,
    raw: Dict[str, Any],
    path: str,
    report: ValidationReport,
    *,
    require_rootflo_uuid: bool,
) -> None:
    """
    Rules the server's agent build enforces on top of the pydantic model.

    ``config`` is the validated model (an agent, or an inline workflow agent, which
    shares its fields) and ``raw`` the matching mapping from the document: tools are
    read from ``raw`` because the model normalises shapes the server's tool loading
    does not accept.
    """
    if config.model is None:
        report.add(
            f'{path}.model',
            "Model must be specified: the server supplies no default LLM, so add a 'model' block",
        )
    elif require_rootflo_uuid and config.model.provider == 'rootflo':
        # A workflow resolves an agent's rootflo model_id to an LLM inference
        # config by UUID, so anything else cannot be resolved when it runs
        try:
            uuid.UUID(str(config.model.model_id))
        except ValueError:
            report.add(
                f'{path}.model.model_id',
                f"RootFlo model_id '{config.model.model_id}' is not the UUID of an LLM inference config",
            )

    tools = raw.get('tools')
    if tools is None:
        return
    if not isinstance(tools, list):
        report.add(
            f'{path}.tools',
            "Tools must be a list of objects, each with a 'name' (for example `- name: my_tool`)",
        )
        return
    for index, tool in enumerate(tools):
        tool_path = f'{path}.tools[{index}]'
        if not isinstance(tool, dict):
            report.add(
                tool_path,
                f"Tool '{tool}' must be an object with a 'name' field (for example `- name: {tool}`); the server cannot load plain tool names",
            )
            continue
        name = tool.get('name')
        if isinstance(name, str) and name:
            report.tool_refs.append(ToolReference(f'{tool_path}.name', name))


def validate_agent_document(
    data: Dict[str, Any],
    report: Optional[ValidationReport] = None,
    *,
    path: str = '',
    require_rootflo_uuid: bool = False,
) -> ValidationReport:
    """
    Validate a parsed agent document (``agent:`` root) against ``AgentYamlModel``
    and the rules the server's agent build adds.

    Args:
        data: The parsed document.
        report: Report to add to; a new one is created when omitted.
        path: Path prefix, for a document embedded in another (``yaml_config``).
        require_rootflo_uuid: Also require a rootflo ``model_id`` to be a UUID. Set
            for agents a workflow builds, which resolve it to an LLM config.
    """
    report = report if report is not None else ValidationReport()

    try:
        model = AgentYamlModel(**data)
    except ValidationError as e:
        report.errors.extend(_pydantic_errors(e, data, path))
        return report
    except (ValueError, TypeError) as e:
        report.add(path, str(e))
        return report

    report.schema_valid = True
    raw_agent = data.get('agent')
    _check_agent_config(
        model.agent,
        raw_agent if isinstance(raw_agent, dict) else {},
        _join(path, 'agent'),
        report,
        require_rootflo_uuid=require_rootflo_uuid,
    )
    return report


class _RouterInfo(NamedTuple):
    targets: List[str]
    self_referencing: bool


def _router_info(router: RouterConfigModel) -> _RouterInfo:
    """The node names a router can return, as ``get_routing_options`` reports them."""
    if router.type == 'smart':
        targets = list((router.routing_options or {}).keys())
    elif router.type == 'task_classifier':
        targets = list((router.task_categories or {}).keys())
    elif router.type == 'conversation_analysis':
        targets = list((router.routing_logic or {}).keys())
    elif router.type == 'reflection':
        targets = list(dict.fromkeys(router.flow_pattern or []))
    elif router.type == 'plan_execute':
        targets = list((router.agents or {}).keys())
    else:  # field_match: every route value, plus the default
        targets = list(
            dict.fromkeys(
                list((router.routes or {}).values())
                + ([router.default] if router.default else [])
            )
        )
    return _RouterInfo(targets, router.type in _SELF_REFERENCING_ROUTERS)


def _validate_level(
    config: Any,
    raw: Dict[str, Any],
    path: str,
    function_names: Optional[Collection[str]],
    report: ValidationReport,
) -> None:
    """
    Graph rules for one arium: the top-level one, or an inline nested one.

    ``config`` is the validated model (``AriumConfigModel`` or
    ``AriumNodeConfigModel``), ``raw`` the matching mapping, and ``path`` where it
    sits in the document. Nested inline ariums are validated recursively, each
    against its own nodes, since the builder builds each as an arium of its own.
    """
    agents = config.agents or []
    function_nodes = config.function_nodes or []
    ariums = config.ariums or []
    iterators = config.iterators or []
    routers = config.routers or []
    # foreach_nodes wins over iterators when both are written (AriumConfigModel)
    iterators_key = 'foreach_nodes' if raw.get('foreach_nodes') else 'iterators'

    # name -> where it is defined. Used for lookups and to report duplicates, which
    # the builder would otherwise resolve by silently keeping the last definition.
    nodes: Dict[str, str] = {}
    arium_node_names = set()

    def declare(name: str, node_path: str) -> None:
        if name == END_NODE:
            report.add(
                f'{node_path}.name',
                "'end' is reserved for edges that finish the workflow and cannot be a node name",
            )
        elif name in nodes:
            report.add(
                f'{node_path}.name',
                f"Duplicate node name '{name}' (already defined at {nodes[name]})",
            )
        else:
            nodes[name] = node_path

    def available() -> str:
        return f'Available nodes: {list(nodes.keys())}'

    raw_agents = raw.get('agents') or []
    for index, agent in enumerate(agents):
        agent_path = f'{path}.agents[{index}]'
        declare(agent.name, agent_path)

        is_reference_only = (
            agent.job is None
            and agent.prompt is None
            and agent.yaml_config is None
            and agent.yaml_file is None
            and agent.model is None
        )
        if is_reference_only:
            # No configuration of its own: the server resolves it as a stored agent
            namespace, _, rest = agent.name.partition('/')
            if not namespace or not rest:
                report.add(
                    f'{agent_path}.name',
                    f"Agent '{agent.name}' has no configuration. Reference a stored agent as 'namespace/name' or define it inline with 'job' and 'model'",
                )
                continue
        elif agent.yaml_file is not None:
            report.add(
                f'{agent_path}.yaml_file',
                "yaml_file is not supported on the server (it has no access to local files). Use 'yaml_config' or reference a stored agent as 'namespace/name'",
            )
            continue
        elif agent.yaml_config is not None:
            embedded, embedded_errors = parse_yaml_document(agent.yaml_config)
            if embedded is None:
                for error in embedded_errors:
                    report.add(f'{agent_path}.yaml_config', error.message)
            else:
                validate_agent_document(
                    embedded,
                    report,
                    path=f'{agent_path}.yaml_config',
                    require_rootflo_uuid=True,
                )
        else:
            raw_agent = raw_agents[index] if index < len(raw_agents) else {}
            _check_agent_config(
                agent,
                raw_agent if isinstance(raw_agent, dict) else {},
                agent_path,
                report,
                require_rootflo_uuid=True,
            )

        if '/' in agent.name:
            try:
                parse_versioned_reference(agent.name.partition('/')[2])
            except ValueError as e:
                report.add(f'{agent_path}.name', str(e))
            else:
                report.agent_refs.append(
                    AgentReference(f'{agent_path}.name', agent.name)
                )

    for index, function_node in enumerate(function_nodes):
        node_path = f'{path}.function_nodes[{index}]'
        declare(function_node.name, node_path)
        if (
            function_names is not None
            and function_node.function_name not in function_names
        ):
            report.add(
                f'{node_path}.function_name',
                f"Function '{function_node.function_name}' is not in the function registry",
            )

    for index, arium in enumerate(ariums):
        node_path = f'{path}.ariums[{index}]'
        declare(arium.name, node_path)
        arium_node_names.add(arium.name)

    for index, iterator in enumerate(iterators):
        declare(iterator.name, f'{path}.{iterators_key}[{index}]')

    # Nested ariums are separate graphs, so they do not affect this level's counts
    raw_ariums = raw.get('ariums') or []
    for index, arium in enumerate(ariums):
        node_path = f'{path}.ariums[{index}]'
        if arium.yaml_file is not None:
            report.add(
                f'{node_path}.yaml_file',
                "yaml_file is not supported on the server (it has no access to local files). Define the workflow inline or reference a stored workflow as 'namespace/name'",
            )
            continue
        raw_arium = raw_ariums[index] if index < len(raw_ariums) else {}
        _validate_level(
            arium,
            raw_arium if isinstance(raw_arium, dict) else {},
            node_path,
            function_names,
            report,
        )

    level_errors_before = len(report.errors)

    router_infos: Dict[str, _RouterInfo] = {}
    for index, router in enumerate(routers):
        if router.name in router_infos:
            report.add(
                f'{path}.routers[{index}].name',
                f"Duplicate router name '{router.name}'",
            )
            continue
        router_infos[router.name] = _router_info(router)

    for index, iterator in enumerate(iterators):
        if iterator.execute_node not in nodes:
            report.add(
                f'{path}.{iterators_key}[{index}].execute_node',
                f"execute_node '{iterator.execute_node}' not found. {available()}",
            )

    workflow = config.workflow
    if workflow is None:
        return
    workflow_path = f'{path}.workflow'

    if not workflow.start:
        report.add(f'{workflow_path}.start', 'Workflow must specify a start node')
    elif workflow.start not in nodes:
        report.add(
            f'{workflow_path}.start',
            f"Start node '{workflow.start}' not found. {available()}",
        )

    used = {workflow.start}
    connected = {workflow.start}
    outgoing: Dict[str, int] = {}

    for index, edge in enumerate(workflow.edges):
        edge_path = f'{workflow_path}.edges[{index}]'
        source = edge.from_
        targets = [target for target in edge.to if target != END_NODE]
        used.add(source)
        used.update(targets)

        if source not in nodes:
            report.add(
                f'{edge_path}.from',
                f"From node '{source}' not found. {available()}",
            )

        targets_known = True
        for target_index, target in enumerate(edge.to):
            if target != END_NODE and target not in nodes:
                targets_known = False
                report.add(
                    f'{edge_path}.to[{target_index}]',
                    f"To node '{target}' not found. {available()}",
                )

        router_info = None
        if edge.router:
            router_info = router_infos.get(edge.router)
            if router_info is None:
                report.add(
                    f'{edge_path}.router',
                    f"Router '{edge.router}' not found. Available routers: {list(router_infos.keys())}",
                )

        if not targets:
            # Only 'end': nothing to wire; the node finishes through workflow.end
            continue

        if not edge.router:
            if len(targets) != 1:
                report.add(
                    f'{edge_path}.to',
                    f"Node '{source}' has {len(targets)} targets but no router. Without a router a node can have exactly one target; add a router to branch",
                )
        elif router_info is not None and source in nodes and targets_known:
            literals = router_info.targets
            if router_info.self_referencing:
                allowed = targets + [source]
                invalid = [value for value in literals if value not in allowed]
                missing = [target for target in targets if target not in literals]
                if invalid:
                    report.add(
                        f'{edge_path}.to',
                        f"Router '{edge.router}' can route to {invalid}, which are not targets of this edge {targets}",
                    )
                if missing:
                    report.add(
                        f'{edge_path}.to',
                        f"Router '{edge.router}' must be able to route to every target of the edge; missing {missing}",
                    )
            elif set(literals) != set(targets):
                report.add(
                    f'{edge_path}.to',
                    f"Router '{edge.router}' routes to {literals} but the edge targets are {targets}; "
                    f'they must match exactly (not on the edge: {[v for v in literals if v not in targets]}, '
                    f'not on the router: {[v for v in targets if v not in literals]})',
                )

        if source in outgoing:
            report.add(
                f'{edge_path}.from',
                f"Node '{source}' already has an outgoing edge at edges[{outgoing[source]}]; "
                f'only one is kept. Use a router to branch from one node',
            )
        else:
            outgoing[source] = index
        connected.add(source)
        connected.update(targets)

    if not workflow.end:
        report.add(f'{workflow_path}.end', 'Workflow must specify end nodes')
    for index, end_name in enumerate(workflow.end):
        end_path = f'{workflow_path}.end[{index}]'
        if end_name not in nodes:
            report.add(end_path, f"End node '{end_name}' not found. {available()}")
            continue
        used.add(end_name)
        connected.add(end_name)
        if end_name in outgoing:
            report.add(
                end_path,
                f"Node '{end_name}' is listed in workflow.end but also has an outgoing edge "
                f'(edges[{outgoing[end_name]}]). The end replaces that edge, so the workflow stops '
                f"at '{end_name}'. Remove it from end, or remove the edge",
            )

    # Orphans only make sense once the edges themselves are sound. A nested arium
    # nothing points at is not part of the graph, so it cannot be an orphan.
    if len(report.errors) == level_errors_before:
        for name, node_path in nodes.items():
            if name in arium_node_names and name not in used:
                continue
            if name not in connected:
                report.add(
                    f'{node_path}.name',
                    f"Node '{name}' has no incoming or outgoing edge and is neither the start nor an end node. "
                    f"Connect it or remove it (a node used only as an iterator's execute_node must be a sub-workflow)",
                )


def validate_arium_document(
    data: Dict[str, Any],
    *,
    function_names: Optional[Collection[str]] = None,
) -> ValidationReport:
    """
    Validate a parsed workflow document (``arium:`` root) against
    ``AriumYamlModel`` and the graph rules the builder enforces.

    Subworkflow references (``namespace/name`` with no body) must already be inlined
    by the caller, as the models require every nested arium to have a body.

    Args:
        data: The parsed document.
        function_names: Names in the function registry; when given, every function
            node must name one of them.
    """
    report = ValidationReport()

    try:
        model = AriumYamlModel(**data)
    except ValidationError as e:
        report.errors.extend(_pydantic_errors(e, data))
        return report
    except (ValueError, TypeError) as e:
        report.add('', str(e))
        return report

    report.schema_valid = True
    raw_arium = data.get('arium')
    _validate_level(
        model.arium,
        raw_arium if isinstance(raw_arium, dict) else {},
        'arium',
        function_names,
        report,
    )
    return report
