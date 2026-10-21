import yaml from 'js-yaml';
import { Node, Edge, MarkerType } from '@xyflow/react';
import dagre from 'dagre';
import { EDGE_KINDS, NODE_TYPES, getEdgeKind } from '@app/constants/workflow-builder';
import {
  AgentConfigMethod,
  AriumAgentConfig,
  AriumDoc,
  AriumFunctionNodeConfig,
  AriumIteratorConfig,
  AriumModelConfig,
  AriumRouterConfig,
  AriumSubworkflowConfig,
  AriumWorkflowConfig,
  AriumWorkflowEdge,
  GraphIssue,
  ParseGraphResult,
  SerializeGraphResult,
} from '@app/types/workflow-builder';

const nodeWidth = 320;
const nodeHeight = 180;

const TRIGGER_NODE_ID = 'trigger-start';
// flo_ai sentinels: `to: [end]` is skipped by the runtime, `input` in input_filter means the user input
const END_SENTINEL = 'end';
const INPUT_SENTINEL = 'input';
const ROOTFLO_PROVIDER = 'rootflo';
const MISSING_ARIUM_ERROR = 'The YAML has no top-level `arium` key';

type Data = Record<string, unknown>;

const isPlainObject = (value: unknown): value is Data =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const hasOwn = (obj: object, key: string) => Object.prototype.hasOwnProperty.call(obj, key);

const unique = <T>(items: T[]): T[] => Array.from(new Set(items));

// A YAML value that may be one name or a list of names, as a list of names
const toNameList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item !== '')
    : typeof value === 'string' && value
      ? [value]
      : [];

// A string-valued mapping (routing_options, routing_logic, agents), with non-string values read as ''
const toStringRecord = (value: unknown): Record<string, string> =>
  isPlainObject(value)
    ? Object.fromEntries(Object.entries(value).map(([key, v]) => [key, typeof v === 'string' ? v : '']))
    : {};

// PyYAML (YAML 1.1, what the server uses) also reads yes/no/on/off as booleans; js-yaml (YAML 1.2) keeps them as strings
const YAML11_TRUE = ['true', 'yes', 'on'];
const YAML11_FALSE = ['false', 'no', 'off'];
const toBool = (value: unknown, fallback: boolean): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (YAML11_TRUE.includes(normalized)) return true;
    if (YAML11_FALSE.includes(normalized)) return false;
  }
  return fallback;
};

// A number the user entered, or undefined when the field is blank or not numeric
const toOptionalNumber = (value: unknown): number | undefined => {
  if (value === '' || value === undefined || value === null) return undefined;
  const n = Number(value);
  return Number.isNaN(n) ? undefined : n;
};

const setOrDelete = (obj: Data, key: string, value: unknown) => {
  if (value === undefined || value === null || value === '') {
    delete obj[key];
  } else {
    obj[key] = value;
  }
};

// Write a boolean flag without injecting its runtime default into YAML that never set it
const patchBoolean = (obj: Data, key: string, value: unknown, runtimeDefault: boolean) => {
  if (typeof value !== 'boolean') return;
  if (value === runtimeDefault && !hasOwn(obj, key)) return;
  obj[key] = value;
};

const describeYamlError = (e: unknown): string => {
  if (e instanceof yaml.YAMLException) {
    return e.mark ? `${e.reason} (line ${e.mark.line + 1})` : e.reason;
  }
  return e instanceof Error ? e.message : String(e);
};

const NODE_LIST_KEYS = ['agents', 'routers', 'function_nodes', 'iterators', 'foreach_nodes', 'ariums'];

// Check that the arium block has the shape the graph is built from, so a malformed document is reported
// instead of being drawn (and saved back) without the parts that could not be read
const validateAriumShape = (arium: unknown): string | undefined => {
  if (!isPlainObject(arium)) return '`arium` must be a mapping';
  for (const key of NODE_LIST_KEYS) {
    const list = arium[key];
    if (list === undefined || list === null) continue;
    if (!Array.isArray(list)) return `\`arium.${key}\` must be a list`;
    const badIndex = list.findIndex((entry) => !isPlainObject(entry) || typeof entry.name !== 'string' || !entry.name);
    if (badIndex >= 0) return `\`arium.${key}[${badIndex}]\` must be a mapping with a \`name\``;
  }
  const workflow = arium.workflow;
  if (workflow === undefined || workflow === null) return undefined;
  if (!isPlainObject(workflow)) return '`arium.workflow` must be a mapping';
  if (workflow.edges === undefined || workflow.edges === null) return undefined;
  if (!Array.isArray(workflow.edges)) return '`arium.workflow.edges` must be a list';
  const badEdge = workflow.edges.findIndex((edge) => !isPlainObject(edge) || typeof edge.from !== 'string');
  if (badEdge >= 0) return `\`arium.workflow.edges[${badEdge}]\` must be a mapping with a \`from\``;
  return undefined;
};

// Mirrors the server's parse_versioned_reference on the last path segment: 'ns/wf@3' -> 'wf'
const parseRefLocalName = (ref: string): string => (ref.split('/').pop() || ref).replace(/@.*$/, '');

// Keys that make an `ariums` entry an inline workflow definition (rather than a reference or a yaml_file)
const INLINE_ARIUM_BODY_KEYS = [
  'agents',
  'function_nodes',
  'routers',
  'ariums',
  'iterators',
  'foreach_nodes',
  'workflow',
];
const YAML_FILE_PATTERN = /\.ya?ml$/i;

const hasInlineBody = (entry: Data): boolean => INLINE_ARIUM_BODY_KEYS.some((key) => entry[key] != null);

// A stored-workflow reference: `name: namespace/workflow[@version]` with no body and no yaml_file (server contract)
const isWorkflowReference = (entry: AriumSubworkflowConfig): boolean =>
  !entry.yaml_file && !hasInlineBody(entry) && entry.name.includes('/');

// The node name an `ariums` entry runs under: the server renames a reference to its local name
const subworkflowNodeName = (entry: AriumSubworkflowConfig): string =>
  isWorkflowReference(entry) ? parseRefLocalName(entry.name) : entry.name;

const getAgentConfigMethod = (agent: AriumAgentConfig): AgentConfigMethod => {
  if (agent.yaml_file) return 'yaml_file';
  if (agent.yaml_config) return 'yaml_config';
  if ((agent.job ?? agent.prompt ?? agent.model) != null) return 'inline';
  return 'reference';
};

const getRouterType = (data: Data): string => (data.strategy as string) || (data.type as string) || 'smart';

export const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 80,
    ranksep: 120,
    marginx: 50,
    marginy: 50,
  });

  const nodeIds = new Set(nodes.map((n) => n.id));

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  // Only layout primary execution edges, NOT memory filters, reflection back-loops, or iterator loop returns.
  // Including data-dependency or cyclic return edges destroys the linear sequential pipeline.
  edges.forEach((edge) => {
    const kind = getEdgeKind(edge);
    if (kind === EDGE_KINDS.FILTER || kind === EDGE_KINDS.REFLECT || kind === EDGE_KINDS.LOOP_RETURN) {
      return;
    }
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      dagreGraph.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    if (!nodeWithPosition) return node;
    return {
      ...node,
      position: {
        x: Math.round(nodeWithPosition.x - nodeWidth / 2),
        y: Math.round(nodeWithPosition.y - nodeHeight / 2),
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

export const createIteratorLoopEdges = (iteratorName: string, executeNode: string): Edge[] => [
  {
    id: `e-loop-exec-${iteratorName}-${executeNode}`,
    source: iteratorName,
    sourceHandle: 'loop-out',
    target: executeNode,
    type: 'smoothstep',
    animated: true,
    style: { stroke: '#6366f1', strokeWidth: 2 },
    label: 'Iterate (1..N) ➔',
    labelStyle: { fill: '#6366f1', fontSize: 9, fontWeight: 700 },
    labelBgStyle: { fill: 'hsl(var(--card))', stroke: '#6366f1', strokeWidth: 1 },
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 4,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#6366f1', width: 14, height: 14 },
    data: { kind: EDGE_KINDS.LOOP_EXEC },
  },
  {
    id: `e-loop-return-${executeNode}-${iteratorName}`,
    source: executeNode,
    sourceHandle: 'loop-back',
    target: iteratorName,
    targetHandle: 'loop-return',
    type: 'smoothstep',
    animated: true,
    style: { stroke: '#818cf8', strokeWidth: 2, strokeDasharray: '5,5' },
    label: '↺ Next Item (Repeat)',
    labelStyle: { fill: '#818cf8', fontSize: 9, fontWeight: 700 },
    labelBgStyle: { fill: 'hsl(var(--card))', stroke: '#818cf8', strokeWidth: 1 },
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 4,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#818cf8', width: 14, height: 14 },
    data: { kind: EDGE_KINDS.LOOP_RETURN },
  },
];

// Visual connection for input_filter (dashed "Filter" edges from each dependency to the node)
const buildFilterEdges = (inputFilter: unknown, targetId: string): Edge[] =>
  toNameList(inputFilter)
    .filter((dep) => dep !== INPUT_SENTINEL)
    .map((dep) => ({
      id: `e-filter-${dep}-${targetId}`,
      source: dep,
      target: targetId,
      type: 'smoothstep',
      animated: false,
      style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
      label: 'Filter',
      labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
      data: { kind: EDGE_KINDS.FILTER },
    }));

const truncateLabel = (text: string): string => (text.length > 25 ? text.substring(0, 25) + '...' : text);

const createRouterRouteEdge = (routerId: string, targetId: string, label: string): Edge => ({
  id: `e-${routerId}-${targetId}`,
  source: routerId,
  target: targetId,
  type: 'smoothstep',
  label,
  labelStyle: { fill: '#ea580c', fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
  labelBgPadding: [6, 4] as [number, number],
  labelBgBorderRadius: 6,
  labelBgStyle: { fill: 'hsl(var(--card))', stroke: '#ea580c', strokeWidth: 1 },
  style: { stroke: '#f97316', strokeWidth: 2 },
  data: { kind: EDGE_KINDS.ROUTE },
});

const processAgents = (agents: AriumAgentConfig[], endNodes: string[], nodes: Node[], edges: Edge[]) => {
  agents.forEach((agent: AriumAgentConfig) => {
    nodes.push({
      id: agent.name,
      type: NODE_TYPES.AGENT,
      position: { x: 0, y: 0 },
      data: {
        label: agent.name,
        // How the YAML defines this agent; only 'inline' agents have their role/job/model written by the canvas
        configMethod: getAgentConfigMethod(agent),
        role: agent.role || '',
        job: agent.job || agent.prompt || '',
        act_as: agent.act_as,
        yaml_file: agent.yaml_file,
        provider: agent.model?.provider || '',
        model: agent.model?.name || '',
        model_id: agent.model?.model_id || '',
        temperature: agent.settings?.temperature,
        max_tokens: agent.settings?.max_tokens,
        tools: agent.tools || [],
        input_filter: agent.input_filter,
        parser: agent.parser,
        isEndNode: endNodes.includes(agent.name),
        type: 'agent',
      },
    });

    edges.push(...buildFilterEdges(agent.input_filter, agent.name));
  });
};

const processFunctionNodes = (
  functionNodes: AriumFunctionNodeConfig[],
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  functionNodes.forEach((fn: AriumFunctionNodeConfig) => {
    nodes.push({
      id: fn.name,
      type: NODE_TYPES.FUNCTION,
      position: { x: 0, y: 0 },
      data: {
        label: fn.name,
        function_name: fn.function_name,
        description: fn.description,
        input_filter: fn.input_filter,
        prefilled_params: fn.prefilled_params,
        isEndNode: endNodes.includes(fn.name),
        type: 'function',
      },
    });

    edges.push(...buildFilterEdges(fn.input_filter, fn.name));
  });
};

const processIterators = (iterators: AriumIteratorConfig[], endNodes: string[], nodes: Node[], edges: Edge[]) => {
  iterators.forEach((it: AriumIteratorConfig) => {
    nodes.push({
      id: it.name,
      type: NODE_TYPES.ITERATOR,
      position: { x: 0, y: 0 },
      data: {
        label: it.name,
        execute_node: it.execute_node,
        input_filter: it.input_filter,
        forward_all_results: toBool(it.forward_all_results, false),
        isEndNode: endNodes.includes(it.name),
        type: 'iterator',
      },
    });

    edges.push(...buildFilterEdges(it.input_filter, it.name));
  });
};

const processSubworkflows = (
  nestedAriums: AriumSubworkflowConfig[],
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  nestedAriums.forEach((arium: AriumSubworkflowConfig) => {
    const nodeName = subworkflowNodeName(arium);
    nodes.push({
      id: nodeName,
      type: NODE_TYPES.SUBWORKFLOW,
      position: { x: 0, y: 0 },
      data: {
        label: nodeName,
        name: nodeName,
        // Exactly one of: ref (stored workflow 'namespace/workflow[@version]'), yaml_file, or an inline body in the YAML
        ref: isWorkflowReference(arium) ? arium.name : undefined,
        yaml_file: arium.yaml_file,
        inherit_variables: toBool(arium.inherit_variables, true),
        input_filter: arium.input_filter,
        isEndNode: endNodes.includes(nodeName),
        type: 'subworkflow',
      },
    });

    edges.push(...buildFilterEdges(arium.input_filter, nodeName));
  });
};

// The branches the canvas draws for a router (target -> condition text), read from the config its type routes on.
// field_match conditions are the matched values, joined with ' | ' when several values lead to one target.
const getRouterBranchOptions = (router: AriumRouterConfig): Record<string, string> => {
  switch (router.type) {
    case 'field_match': {
      const options: Record<string, string> = {};
      if (isPlainObject(router.routes)) {
        Object.entries(router.routes).forEach(([value, target]) => {
          if (typeof target !== 'string' || !target) return;
          options[target] = hasOwn(options, target) && options[target] ? `${options[target]} | ${value}` : value;
        });
      }
      if (typeof router.default === 'string' && router.default && !hasOwn(options, router.default)) {
        options[router.default] = '';
      }
      return options;
    }
    case 'task_classifier':
      return isPlainObject(router.task_categories)
        ? Object.fromEntries(
            Object.entries(router.task_categories).map(([target, category]) => [
              target,
              isPlainObject(category) && typeof category.description === 'string' ? category.description : '',
            ])
          )
        : {};
    case 'conversation_analysis':
      return toStringRecord(router.routing_logic);
    case 'plan_execute':
      return toStringRecord(router.agents);
    case 'reflection':
      return Object.fromEntries(unique(toNameList(router.flow_pattern)).map((step) => [step, 'Reflection step']));
    default:
      return toStringRecord(router.routing_options);
  }
};

// Process Routers (Smart, Field Match, Reflection, Task Classifier, etc.)
const processRouters = (routers: AriumRouterConfig[], endNodes: string[], nodes: Node[], edges: Edge[]) => {
  routers.forEach((router: AriumRouterConfig) => {
    const routerType = router.type || 'smart';
    const flowPattern = toNameList(router.flow_pattern);
    const allowEarlyExit = router.settings?.allow_early_exit;

    nodes.push({
      id: router.name,
      type: NODE_TYPES.ROUTER,
      position: { x: 0, y: 0 },
      data: {
        label: router.name,
        strategy: routerType,
        type: routerType,
        field: router.field,
        default: router.default,
        flow_pattern: router.flow_pattern === undefined ? undefined : flowPattern,
        allow_early_exit: allowEarlyExit === undefined ? undefined : toBool(allowEarlyExit, false),
        provider: router.model?.provider || '',
        model: router.model?.name || '',
        model_id: router.model?.model_id || '',
        temperature: router.settings?.temperature,
        context_description: router.settings?.context_description || '',
        fallback_strategy: router.settings?.fallback_strategy,
        routing_options: getRouterBranchOptions(router),
        isEndNode: endNodes.includes(router.name),
      },
    });

    // Reflection flow visual loops
    if (routerType === 'reflection' && flowPattern.length > 1) {
      for (let i = 0; i < flowPattern.length - 1; i++) {
        const from = flowPattern[i];
        const to = flowPattern[i + 1];
        edges.push({
          id: `e-reflect-${router.name}-${from}-${to}-${i}`,
          source: from,
          target: to,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#f43f5e', strokeWidth: 1.5, strokeDasharray: '5,5' },
          label: `Loop #${i + 1}`,
          labelStyle: { fill: '#f43f5e', fontSize: 9 },
          data: { kind: EDGE_KINDS.REFLECT },
        });
      }
    }
  });
};

// Connect ForEach Iterator Loops (Forward Item & Return Cycle)
// Must run after every node has been added: it looks up the execute node and tags it as a loop target.
const connectIteratorLoops = (iterators: AriumIteratorConfig[], nodes: Node[], edges: Edge[]) => {
  iterators.forEach((it: AriumIteratorConfig) => {
    if (it.execute_node) {
      const targetNode = nodes.find((n: Node) => n.id === it.execute_node);
      if (targetNode) {
        targetNode.data = {
          ...targetNode.data,
          isLoopTarget: true,
          loopedBy: it.name,
        };
      }

      edges.push(...createIteratorLoopEdges(it.name, it.execute_node));
    }
  });
};

// Add Start Trigger
const addStartTrigger = (workflow: AriumWorkflowConfig, nodes: Node[], edges: Edge[]) => {
  if (workflow.start) {
    nodes.push({
      id: TRIGGER_NODE_ID,
      type: NODE_TYPES.TRIGGER,
      position: { x: 0, y: 0 },
      data: {
        label: 'Workflow Trigger',
        schema: '{\n  "event": "start"\n}',
        type: 'trigger',
      },
    });

    edges.push({
      id: `e-start-${workflow.start}`,
      source: TRIGGER_NODE_ID,
      target: workflow.start,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#a855f7', strokeWidth: 2 },
      data: { kind: EDGE_KINDS.START },
    });
  }
};

const pushUniqueEdge = (edges: Edge[], edge: Edge) => {
  if (!edges.some((e) => e.id === edge.id)) edges.push(edge);
};

// Connect from -> router, then router -> each target (adds missing targets to the router node's routing_options)
const addRouterEdges = (from: string, router: string, toList: string[], nodes: Node[], edges: Edge[]) => {
  // Connect from -> router
  pushUniqueEdge(edges, {
    id: `e-${from}-${router}`,
    source: from,
    target: router,
    type: 'smoothstep',
    animated: true,
    style: { stroke: '#64748b', strokeWidth: 2 },
    data: { kind: EDGE_KINDS.FLOW },
  });

  // Connect router -> to
  const routerNode = nodes.find((n: Node) => n.id === router);
  const routerOpts = (routerNode?.data?.routing_options as Record<string, string>) || {};

  toList.forEach((toItem: string) => {
    if (!hasOwn(routerOpts, toItem)) {
      routerOpts[toItem] = `Route to ${toItem}`;
      if (routerNode) {
        routerNode.data.routing_options = routerOpts;
      }
    }
    pushUniqueEdge(edges, createRouterRouteEdge(router, toItem, truncateLabel(routerOpts[toItem] || `to ${toItem}`)));
  });
};

// Direct connect from -> each target
const addDirectEdges = (from: string, toList: string[], iterators: AriumIteratorConfig[], edges: Edge[]) => {
  const isFromIterator = iterators.some((it: AriumIteratorConfig) => it.name === from);
  toList.forEach((toItem: string) => {
    pushUniqueEdge(edges, {
      id: `e-${from}-${toItem}`,
      source: from,
      target: toItem,
      type: 'smoothstep',
      animated: true,
      style: { stroke: isFromIterator ? '#6366f1' : '#64748b', strokeWidth: 2 },
      label: isFromIterator ? 'On Complete [All]' : undefined,
      labelStyle: isFromIterator ? { fill: '#6366f1', fontSize: 9, fontWeight: 600 } : undefined,
      labelBgStyle: isFromIterator ? { fill: 'hsl(var(--card))', stroke: '#6366f1', strokeWidth: 1 } : undefined,
      labelBgPadding: isFromIterator ? ([6, 3] as [number, number]) : undefined,
      labelBgBorderRadius: isFromIterator ? 4 : undefined,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isFromIterator ? '#6366f1' : '#64748b',
        width: 14,
        height: 14,
      },
      data: { kind: EDGE_KINDS.FLOW },
    });
  });
};

// Process Edges from Workflow
const processWorkflowEdges = (
  workflow: AriumWorkflowConfig,
  iterators: AriumIteratorConfig[],
  nodes: Node[],
  edges: Edge[]
) => {
  (workflow.edges || []).forEach((edgeObj: AriumWorkflowEdge) => {
    // `end` is a runtime sentinel, not a node: termination is expressed by workflow.end
    const toList = toNameList(edgeObj.to).filter((to) => to !== END_SENTINEL);

    if (edgeObj.router) {
      addRouterEdges(edgeObj.from, edgeObj.router, toList, nodes, edges);
    } else {
      addDirectEdges(edgeObj.from, toList, iterators, edges);
    }
  });
};

// Implicit edges from routing_options that might be missing in workflow.edges
const addImplicitRouterEdges = (nodes: Node[], edges: Edge[]) => {
  const nodeIds = new Set(nodes.map((n) => n.id));
  nodes
    .filter((n) => n.type === NODE_TYPES.ROUTER)
    .forEach((routerNode) => {
      const opts = toStringRecord(routerNode.data.routing_options);
      Object.keys(opts).forEach((targetName) => {
        if (!nodeIds.has(targetName)) return;
        pushUniqueEdge(
          edges,
          createRouterRouteEdge(routerNode.id, targetName, truncateLabel(opts[targetName] || `to ${targetName}`))
        );
      });
    });
};

// Build the canvas graph from workflow YAML. Empty YAML gives an empty graph.
// `error` is set (with an empty graph) when the YAML cannot be drawn faithfully; callers must show it and must not
// let the user edit or save the empty canvas over the YAML.
export const parseYamlToGraph = (yamlString: string): ParseGraphResult => {
  let doc: unknown;
  try {
    doc = yamlString.trim() ? yaml.load(yamlString) : null;
  } catch (e) {
    return { nodes: [], edges: [], error: describeYamlError(e) };
  }
  if (doc === null || doc === undefined) return { nodes: [], edges: [] };
  if (!isPlainObject(doc) || doc.arium === undefined || doc.arium === null) {
    return { nodes: [], edges: [], error: MISSING_ARIUM_ERROR };
  }
  const shapeError = validateAriumShape(doc.arium);
  if (shapeError) return { nodes: [], edges: [], error: shapeError };

  try {
    const arium = (doc as AriumDoc).arium!;
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    const agents = arium.agents || [];
    const routers = arium.routers || [];
    const functionNodes = arium.function_nodes || [];
    // flo_ai prefers foreach_nodes when both aliases are present
    const iterators = arium.foreach_nodes || arium.iterators || [];
    const nestedAriums = arium.ariums || [];
    const workflow = arium.workflow || { edges: [] };
    const endNodes = toNameList(workflow.end);

    // 1. Process Agents
    processAgents(agents, endNodes, nodes, edges);

    // 2. Process Function Nodes
    processFunctionNodes(functionNodes, endNodes, nodes, edges);

    // 3. Process Iterators / ForEach
    processIterators(iterators, endNodes, nodes, edges);

    // 4. Process Sub-Workflows (Nested Ariums)
    processSubworkflows(nestedAriums, endNodes, nodes, edges);

    // 5. Process Routers (Smart, Field Match, Reflection, Task Classifier, etc.)
    processRouters(routers, endNodes, nodes, edges);

    // 6. Connect ForEach Iterator Loops (Forward Item & Return Cycle)
    connectIteratorLoops(iterators, nodes, edges);

    // 7. Add Start Trigger
    addStartTrigger(workflow, nodes, edges);

    // 8. Process Edges from Workflow
    processWorkflowEdges(workflow, iterators, nodes, edges);

    // Implicit edges from routing_options that might be missing in workflow.edges
    addImplicitRouterEdges(nodes, edges);

    return getLayoutedElements(nodes, edges);
  } catch (e) {
    return { nodes: [], edges: [], error: describeYamlError(e) };
  }
};

// ---------------------------------------------------------------------------
// Serialization: patch the loaded YAML document. Each entry starts from the YAML it was parsed from and only the
// keys the canvas owns are written, so provider blocks, yaml_file references and unknown keys survive every edit.
// ---------------------------------------------------------------------------

// Node types that flo_ai resolves by name (start, edge from/to, end, execute_node, input_filter).
// Routers are not nodes at runtime: they only appear on edges.
const SOURCE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
];

const isSourceNode = (node?: Node): boolean => !!node && SOURCE_NODE_TYPES.includes(node.type || '');

interface SerializeContext {
  sourceIds: Set<string>;
  issues: GraphIssue[];
}

const report = (ctx: SerializeContext, message: string, nodeId?: string) => {
  ctx.issues.push(nodeId ? { message, nodeId } : { message });
};

const quoteList = (names: string[]) => names.map((name) => `"${name}"`).join(', ');

// The YAML entry a node was parsed from, as a copy to patch (empty for a new node).
// A renamed node keeps the name it is stored under in data.yamlName until the editor settles it after a serialize.
const findSourceEntry = <T extends { name: string }>(
  entries: T[],
  node: Node,
  nameOf: (entry: T) => string = (entry) => entry.name
): Data => {
  const yamlName = (node.data.yamlName as string) || node.id;
  const entry = entries.find((e) => nameOf(e) === yamlName);
  return entry ? ({ ...entry } as Data) : {};
};

// Keep input_filter only when it is a non-empty list
const applyInputFilter = (obj: Data, node: Node, ctx: SerializeContext) => {
  const inputFilter = toNameList(node.data.input_filter);
  if (inputFilter.length === 0) {
    delete obj.input_filter;
    return;
  }
  obj.input_filter = inputFilter;
  const missing = inputFilter.filter((dep) => dep !== INPUT_SENTINEL && !ctx.sourceIds.has(dep));
  if (missing.length > 0) {
    report(ctx, `"${node.id}" reads the output of ${quoteList(missing)}, which is not in this workflow`, node.id);
  }
};

// The model block to save. The node's provider / model / model_id are compared with the block it was parsed from:
// an untouched node keeps that block exactly (any provider, extra keys), and a node that never had one gets none.
// A newly chosen RootFlo model is written as {provider: rootflo, model_id}; model_id is never derived from a model name.
const buildModelBlock = (sourceModel: unknown, data: Data): AriumModelConfig | undefined => {
  const source = isPlainObject(sourceModel) ? (sourceModel as AriumModelConfig) : undefined;
  const modelId = (data.model_id as string) || '';
  const name = (data.model as string) || '';
  const provider = (data.provider as string) || (modelId ? ROOTFLO_PROVIDER : '');

  if (provider === (source?.provider || '') && modelId === (source?.model_id || '') && name === (source?.name || '')) {
    return source;
  }
  if (!provider) return undefined;

  if (provider === ROOTFLO_PROVIDER) {
    if (!modelId) return undefined;
    const model: AriumModelConfig = source?.provider === ROOTFLO_PROVIDER ? { ...source } : {};
    delete model.name;
    return { ...model, provider: ROOTFLO_PROVIDER, model_id: modelId };
  }

  if (!name) return undefined;
  const model: AriumModelConfig = source?.provider === provider ? { ...source } : {};
  delete model.model_id;
  return { ...model, provider, name };
};

// Patch a settings block: undefined values remove their key, and an empty block is dropped
const patchSettings = (sourceSettings: unknown, patch: Data): Data | undefined => {
  const settings: Data = isPlainObject(sourceSettings) ? { ...sourceSettings } : {};
  Object.entries(patch).forEach(([key, value]) => setOrDelete(settings, key, value));
  return Object.keys(settings).length > 0 ? settings : undefined;
};

const toPositiveNumber = (value: unknown): number | undefined => {
  const n = toOptionalNumber(value);
  return n !== undefined && n > 0 ? n : undefined;
};

// Reconstruct Agents
const serializeAgent = (n: Node, existing: Data, ctx: SerializeContext): Data => {
  const agentObj: Data = { ...existing, name: n.id };
  applyInputFilter(agentObj, n, ctx);

  const job = typeof n.data.job === 'string' ? n.data.job : '';
  const modelId = (n.data.model_id as string) || '';
  const parsedMethod = (n.data.configMethod as AgentConfigMethod | undefined) || 'inline';
  // A stored-agent reference that is given a job or a model on the canvas becomes an inline agent
  const method = parsedMethod === 'reference' && (job || modelId) ? 'inline' : parsedMethod;

  if (method === 'reference') return agentObj;

  if (method === 'yaml_file' || method === 'yaml_config') {
    if (job || modelId !== ((existing.model as AriumModelConfig | undefined)?.model_id || '')) {
      report(
        ctx,
        `Agent "${n.id}" is defined by its ${method}; its job and model are edited there, so canvas changes to them are not saved`,
        n.id
      );
    }
    return agentObj;
  }

  // Write the instructions back under the key the YAML used (job or prompt)
  const jobKey = hasOwn(existing, 'prompt') && !hasOwn(existing, 'job') ? 'prompt' : 'job';
  setOrDelete(agentObj, jobKey, job || undefined);
  if (!job) report(ctx, `Agent "${n.id}" needs a job (its instructions)`, n.id);

  setOrDelete(agentObj, 'role', n.data.role || undefined);
  setOrDelete(agentObj, 'act_as', n.data.act_as || undefined);

  const model = buildModelBlock(existing.model, n.data);
  setOrDelete(agentObj, 'model', model);
  if (!model) report(ctx, `Agent "${n.id}" has no model selected`, n.id);

  setOrDelete(
    agentObj,
    'settings',
    patchSettings(existing.settings, {
      temperature: toOptionalNumber(n.data.temperature),
      max_tokens: toPositiveNumber(n.data.max_tokens),
    })
  );

  setOrDelete(agentObj, 'tools', Array.isArray(n.data.tools) && n.data.tools.length > 0 ? n.data.tools : undefined);
  setOrDelete(agentObj, 'parser', n.data.parser || undefined);

  return agentObj;
};

// Reconstruct Function Nodes
const serializeFunctionNode = (n: Node, existing: Data, ctx: SerializeContext): Data => {
  const functionName = typeof n.data.function_name === 'string' ? n.data.function_name.trim() : '';
  const fnObj: Data = { ...existing, name: n.id, function_name: functionName };
  if (!functionName) report(ctx, `Function node "${n.id}" has no function selected`, n.id);

  setOrDelete(fnObj, 'description', n.data.description || undefined);
  applyInputFilter(fnObj, n, ctx);

  const params = n.data.prefilled_params;
  if (isPlainObject(params)) {
    fnObj.prefilled_params = params;
  } else if (params === undefined || params === null || params === '') {
    delete fnObj.prefilled_params;
  } else {
    // Keep what the YAML had rather than saving a value the runtime rejects
    report(ctx, `Function node "${n.id}": prefilled params must be a JSON object`, n.id);
  }

  return fnObj;
};

// Reconstruct Iterators
const serializeIterator = (n: Node, existing: Data, ctx: SerializeContext): Data => {
  const executeNode = typeof n.data.execute_node === 'string' ? n.data.execute_node : '';
  const itObj: Data = { ...existing, name: n.id, execute_node: executeNode };
  if (!executeNode) {
    report(ctx, `Iterator "${n.id}" has no node to run for each item`, n.id);
  } else if (!ctx.sourceIds.has(executeNode)) {
    report(ctx, `Iterator "${n.id}" runs "${executeNode}", which is not in this workflow`, n.id);
  }

  patchBoolean(itObj, 'forward_all_results', n.data.forward_all_results, false);
  applyInputFilter(itObj, n, ctx);

  return itObj;
};

// Reconstruct Sub-Workflows (Ariums)
// A stored workflow is saved as `name: namespace/workflow[@version]` with no yaml_file (what the server inlines),
// a *.yaml / *.yml value as `yaml_file`, and an entry with neither keeps its inline body.
const serializeSubworkflow = (n: Node, existing: Data, ctx: SerializeContext): Data => {
  const ariumObj: Data = { ...existing, name: n.id };
  const reference = String(n.data.ref || n.data.yaml_file || '').trim();

  if (reference) {
    INLINE_ARIUM_BODY_KEYS.forEach((key) => delete ariumObj[key]);
    // A file the YAML already referenced stays a file even without a .yaml suffix (parsed files set only data.yaml_file)
    const isFile = YAML_FILE_PATTERN.test(reference) || (!n.data.ref && existing.yaml_file === reference);
    if (isFile) {
      ariumObj.yaml_file = reference;
    } else {
      delete ariumObj.yaml_file;
      ariumObj.name = reference;
      const localName = parseRefLocalName(reference);
      if (!reference.includes('/')) {
        report(ctx, `Subworkflow "${n.id}": "${reference}" is not a workflow reference (use namespace/workflow)`, n.id);
      } else if (localName !== n.id) {
        report(
          ctx,
          `Subworkflow "${n.id}" references "${reference}", which runs as "${localName}": rename the node to "${localName}" so its connections match`,
          n.id
        );
      }
    }
  } else if (!hasInlineBody(existing)) {
    delete ariumObj.yaml_file;
    report(ctx, `Subworkflow "${n.id}" has no workflow selected`, n.id);
  }

  patchBoolean(ariumObj, 'inherit_variables', n.data.inherit_variables, true);
  applyInputFilter(ariumObj, n, ctx);

  return ariumObj;
};

// Config keys each router type routes on (flo_ai RouterConfigModel)
const ROUTER_TYPE_KEYS: Record<string, string[]> = {
  smart: ['routing_options'],
  task_classifier: ['task_categories'],
  conversation_analysis: ['routing_logic'],
  reflection: ['flow_pattern'],
  plan_execute: ['agents'],
  field_match: ['field', 'routes', 'default'],
};

// Router types whose runtime may route back to the node that called them
const SELF_REFERENCING_ROUTER_TYPES = ['reflection', 'plan_execute'];
const FALLBACK_STRATEGIES = ['first', 'random', 'all'];

// Every node a serialized router can route to. flo_ai requires an edge's `to` to match this set exactly.
const getRouterTargets = (router: Data): string[] => {
  switch (router.type) {
    case 'field_match':
      return unique(
        [...Object.values(isPlainObject(router.routes) ? router.routes : {}), router.default].filter(
          (target): target is string => typeof target === 'string' && target !== ''
        )
      );
    case 'task_classifier':
      return Object.keys(isPlainObject(router.task_categories) ? router.task_categories : {});
    case 'conversation_analysis':
      return Object.keys(isPlainObject(router.routing_logic) ? router.routing_logic : {});
    case 'plan_execute':
      return Object.keys(isPlainObject(router.agents) ? router.agents : {});
    case 'reflection':
      return unique(toNameList(router.flow_pattern));
    default:
      return Object.keys(isPlainObject(router.routing_options) ? router.routing_options : {});
  }
};

// field_match routes (value -> target) from the canvas branches, whose conditions hold the matched values
// separated by '|'. A branch with no value is only valid as the default target.
const buildFieldMatchRoutes = (n: Node, ctx: SerializeContext, fallback: string | undefined) => {
  const routes: Record<string, string> = {};
  Object.entries(toStringRecord(n.data.routing_options)).forEach(([target, condition]) => {
    const values = condition
      .split('|')
      .map((value) => value.trim())
      .filter(Boolean);
    if (values.length === 0 && target !== fallback) {
      report(ctx, `Field-match router "${n.id}": the branch to "${target}" has no value to match`, n.id);
    }
    values.forEach((value) => {
      if (hasOwn(routes, value) && routes[value] !== target) {
        report(ctx, `Field-match router "${n.id}": the value "${value}" is used by more than one branch`, n.id);
      }
      routes[value] = target;
    });
  });
  return routes;
};

// Reconstruct Routers
const serializeRouter = (n: Node, existing: Data, ctx: SerializeContext): Data => {
  const routerType = getRouterType(n.data);
  const routerObj: Data = { ...existing, name: n.id, type: routerType };
  const ownKeys = ROUTER_TYPE_KEYS[routerType];
  if (!ownKeys) {
    report(ctx, `Router "${n.id}" has an unknown type "${routerType}"`, n.id);
    return routerObj;
  }

  // The strategy changed: drop the config of the previous type, which the new type would ignore
  if ((existing.type ?? 'smart') !== routerType) {
    Object.values(ROUTER_TYPE_KEYS)
      .flat()
      .filter((key) => !ownKeys.includes(key))
      .forEach((key) => delete routerObj[key]);
  }

  const drawnTargets = Object.keys(toStringRecord(n.data.routing_options));

  if (routerType === 'field_match') {
    const field = typeof n.data.field === 'string' ? n.data.field.trim() : '';
    const fallback = typeof n.data.default === 'string' && n.data.default ? n.data.default : undefined;
    const routes = buildFieldMatchRoutes(n, ctx, fallback);
    setOrDelete(routerObj, 'field', field || undefined);
    setOrDelete(routerObj, 'routes', Object.keys(routes).length > 0 ? routes : undefined);
    setOrDelete(routerObj, 'default', fallback);
    // Deterministic router: no model, settings or LLM routing options
    delete routerObj.routing_options;
    delete routerObj.model;
    delete routerObj.settings;
    if (!field) report(ctx, `Field-match router "${n.id}" needs the JSON field to match on`, n.id);
    if (Object.keys(routes).length === 0) report(ctx, `Field-match router "${n.id}" needs at least one branch`, n.id);
    if (fallback && !drawnTargets.includes(fallback)) {
      report(ctx, `Field-match router "${n.id}": the default target "${fallback}" is not connected as a branch`, n.id);
    }
  } else {
    if (routerType === 'smart') {
      const routingOptions = toStringRecord(n.data.routing_options);
      setOrDelete(routerObj, 'routing_options', drawnTargets.length > 0 ? routingOptions : undefined);
      if (drawnTargets.length === 0) report(ctx, `Smart router "${n.id}" needs at least one branch`, n.id);
    } else if (routerType === 'reflection') {
      const flowPattern = toNameList(n.data.flow_pattern);
      setOrDelete(routerObj, 'flow_pattern', flowPattern.length > 0 ? flowPattern : undefined);
      if (flowPattern.length === 0) report(ctx, `Reflection router "${n.id}" needs a flow pattern`, n.id);
    } else {
      const configKey = ownKeys[0];
      const configured = getRouterTargets(routerObj);
      if (configured.length === 0) {
        report(ctx, `Router "${n.id}" needs \`${configKey}\`: set it in the YAML editor`, n.id);
      } else {
        const notConfigured = drawnTargets.filter((target) => !configured.includes(target));
        const notDrawn = configured.filter((target) => !drawnTargets.includes(target));
        if (notConfigured.length > 0 || notDrawn.length > 0) {
          report(
            ctx,
            `Router "${n.id}" routes by its \`${configKey}\` (${quoteList(configured)}); change its branches in the YAML editor`,
            n.id
          );
        }
      }
    }

    setOrDelete(routerObj, 'model', buildModelBlock(existing.model, n.data));

    const fallbackStrategy = (n.data.fallback_strategy as string) || undefined;
    if (fallbackStrategy && !FALLBACK_STRATEGIES.includes(fallbackStrategy)) {
      report(ctx, `Router "${n.id}": fallback strategy "${fallbackStrategy}" is not supported`, n.id);
    }
    const settingsPatch: Data = {
      temperature: toOptionalNumber(n.data.temperature),
      fallback_strategy:
        fallbackStrategy && FALLBACK_STRATEGIES.includes(fallbackStrategy) ? fallbackStrategy : undefined,
    };
    if (routerType === 'smart') settingsPatch.context_description = n.data.context_description || undefined;
    if (typeof n.data.allow_early_exit === 'boolean') {
      const sourceSettings = isPlainObject(existing.settings) ? existing.settings : {};
      // Don't write the runtime default (false) into YAML that never set it
      settingsPatch.allow_early_exit =
        n.data.allow_early_exit || hasOwn(sourceSettings, 'allow_early_exit') ? n.data.allow_early_exit : undefined;
    }
    setOrDelete(routerObj, 'settings', patchSettings(existing.settings, settingsPatch));
  }

  const missing = getRouterTargets(routerObj).filter((target) => !ctx.sourceIds.has(target));
  if (missing.length > 0) {
    report(ctx, `Router "${n.id}" routes to ${quoteList(missing)}, which is not in this workflow`, n.id);
  }

  return routerObj;
};

// Build workflow.edges from the canvas flow edges. flo_ai keeps one edge per `from` node, and a plain edge must have
// exactly one target, so a node continues to one node or one router; a router's `to` is the router's full target set.
const buildWorkflowEdges = (
  nodes: Node[],
  edges: Edge[],
  routersById: Map<string, Data>,
  ctx: SerializeContext
): AriumWorkflowEdge[] => {
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const workflowEdges: AriumWorkflowEdge[] = [];

  nodes.filter(isSourceNode).forEach((source) => {
    const targets = unique(
      edges
        .filter((e) => e.source === source.id && getEdgeKind(e) === EDGE_KINDS.FLOW)
        .map((e) => e.target)
        .filter((targetId) => {
          const target = nodesById.get(targetId);
          return isSourceNode(target) || target?.type === NODE_TYPES.ROUTER;
        })
    );
    if (targets.length === 0) return;
    if (targets.length > 1) {
      report(
        ctx,
        `"${source.id}" connects to ${quoteList(targets)}, but a node can continue to only one node: add a router to branch`,
        source.id
      );
    }

    const targetId = targets[0];
    const router = routersById.get(targetId);
    if (!router) {
      workflowEdges.push({ from: source.id, to: [targetId] });
      return;
    }

    let to = getRouterTargets(router);
    if (SELF_REFERENCING_ROUTER_TYPES.includes(router.type as string)) {
      const others = to.filter((target) => target !== source.id);
      if (others.length > 0) to = others;
    }
    if (to.length === 0) {
      report(ctx, `Router "${targetId}" has no branches, so "${source.id}" cannot continue through it`, targetId);
      return;
    }
    workflowEdges.push({ from: source.id, router: targetId, to });
  });

  return workflowEdges;
};

// Resolve workflow.start: the trigger edge, then the YAML's start if that node still exists, then the first node
// nothing leads to (agents first)
const resolveWorkflowStart = (
  nodes: Node[],
  edges: Edge[],
  existingStart: unknown,
  workflowEdges: AriumWorkflowEdge[],
  ctx: SerializeContext
): string | undefined => {
  const startEdge = edges.find((e) => getEdgeKind(e) === EDGE_KINDS.START);
  if (startEdge) {
    if (ctx.sourceIds.has(startEdge.target)) return startEdge.target;
    if (nodes.some((n) => n.id === startEdge.target)) {
      report(ctx, 'The workflow must start at an agent, function, iterator or subworkflow', startEdge.target);
    }
  }
  if (typeof existingStart === 'string' && ctx.sourceIds.has(existingStart)) return existingStart;

  const withIncoming = new Set(workflowEdges.flatMap((e) => toNameList(e.to)));
  const entryCandidates = nodes.filter((n) => isSourceNode(n) && !withIncoming.has(n.id));
  const fallback =
    entryCandidates.find((n) => n.type === NODE_TYPES.AGENT) ?? entryCandidates[0] ?? nodes.find(isSourceNode);
  if (!fallback) report(ctx, 'The workflow has no start node');
  return fallback?.id;
};

// workflow.end: every reachable node with no outgoing edge. flo_ai's add_end_to replaces a node's edge, so a node that
// continues elsewhere must never be an end. Unconnected nodes are reported instead of being made ends.
const buildWorkflowEnds = (
  nodes: Node[],
  workflowEdges: AriumWorkflowEdge[],
  start: string | undefined,
  ctx: SerializeContext
): string[] => {
  const nextById = new Map(workflowEdges.map((e) => [e.from, toNameList(e.to)]));
  const reachable = new Set<string>();
  const queue = start ? [start] : [];
  while (queue.length > 0) {
    const id = queue.shift()!;
    if (reachable.has(id)) continue;
    reachable.add(id);
    queue.push(...(nextById.get(id) || []));
  }

  // An iterator runs its execute_node itself, outside workflow edges
  const executeNodeIds = new Set(
    nodes
      .filter((n) => n.type === NODE_TYPES.ITERATOR)
      .map((n) => n.data.execute_node)
      .filter((id): id is string => typeof id === 'string' && id !== '')
  );

  const ends: string[] = [];
  nodes.filter(isSourceNode).forEach((n) => {
    const isTerminal = !nextById.has(n.id);
    if (reachable.has(n.id)) {
      if (isTerminal) ends.push(n.id);
    } else if (executeNodeIds.has(n.id)) {
      // Agents and function nodes are always registered with the runtime, so a body-only one needs an end edge to not
      // be rejected as an orphan; the edge is never taken because the iterator calls the node directly.
      if (isTerminal && (n.type === NODE_TYPES.AGENT || n.type === NODE_TYPES.FUNCTION)) ends.push(n.id);
    } else if (start) {
      report(ctx, `"${n.id}" is not connected to the workflow, so it never runs`, n.id);
    }
  });

  if (start && ends.length === 0) {
    report(ctx, 'The workflow never ends: every node continues to another node');
  }
  return ends;
};

const setList = (target: Data, key: string, items: Data[]) => {
  if (items.length > 0) {
    target[key] = items;
  } else {
    delete target[key];
  }
};

// Write the canvas graph into `currentYaml`. Only keys the canvas owns are written; everything else is preserved.
// Returns ok:false (and nothing to save) when `currentYaml` itself cannot be read; otherwise the new YAML plus the
// issues that will make the saved workflow fail or run differently from the canvas.
export const serializeGraphToYaml = (nodes: Node[], edges: Edge[], currentYaml: string): SerializeGraphResult => {
  let doc: Data;
  try {
    const loaded = currentYaml.trim() ? yaml.load(currentYaml) : null;
    if (loaded === null || loaded === undefined) {
      doc = {};
    } else if (!isPlainObject(loaded)) {
      return { ok: false, error: MISSING_ARIUM_ERROR };
    } else {
      doc = loaded;
    }
  } catch (e) {
    return { ok: false, error: describeYamlError(e) };
  }

  if (doc.arium === undefined || doc.arium === null) {
    // Only an empty document gets a new arium block; anything else is not a workflow and is left alone
    if (Object.keys(doc).length > 0) return { ok: false, error: MISSING_ARIUM_ERROR };
    doc.arium = {};
  }
  const shapeError = validateAriumShape(doc.arium);
  if (shapeError) return { ok: false, error: shapeError };

  try {
    const arium = doc.arium as Data;
    const ctx: SerializeContext = {
      sourceIds: new Set(nodes.filter(isSourceNode).map((n) => n.id)),
      issues: [],
    };
    const nodesOfType = (type: string) => nodes.filter((n) => n.type === type);

    // 1. Agents
    const sourceAgents = (arium.agents as AriumAgentConfig[] | undefined) || [];
    setList(
      arium,
      'agents',
      nodesOfType(NODE_TYPES.AGENT).map((n) => serializeAgent(n, findSourceEntry(sourceAgents, n), ctx))
    );

    // 2. Function Nodes
    const sourceFunctions = (arium.function_nodes as AriumFunctionNodeConfig[] | undefined) || [];
    setList(
      arium,
      'function_nodes',
      nodesOfType(NODE_TYPES.FUNCTION).map((n) => serializeFunctionNode(n, findSourceEntry(sourceFunctions, n), ctx))
    );

    // 3. Iterators, under the alias the YAML uses (flo_ai prefers foreach_nodes and ignores iterators when both exist)
    const iteratorKey = arium.foreach_nodes ? 'foreach_nodes' : 'iterators';
    const sourceIterators = (arium[iteratorKey] as AriumIteratorConfig[] | undefined) || [];
    delete arium[iteratorKey === 'foreach_nodes' ? 'iterators' : 'foreach_nodes'];
    setList(
      arium,
      iteratorKey,
      nodesOfType(NODE_TYPES.ITERATOR).map((n) => serializeIterator(n, findSourceEntry(sourceIterators, n), ctx))
    );

    // 4. Sub-Workflows (Ariums), matched by the node name each entry runs under
    const sourceAriums = (arium.ariums as AriumSubworkflowConfig[] | undefined) || [];
    setList(
      arium,
      'ariums',
      nodesOfType(NODE_TYPES.SUBWORKFLOW).map((n) =>
        serializeSubworkflow(n, findSourceEntry(sourceAriums, n, subworkflowNodeName), ctx)
      )
    );

    // 5. Routers
    const sourceRouters = (arium.routers as AriumRouterConfig[] | undefined) || [];
    const routersById = new Map<string, Data>();
    nodesOfType(NODE_TYPES.ROUTER).forEach((n) => {
      routersById.set(n.id, serializeRouter(n, findSourceEntry(sourceRouters, n), ctx));
    });
    setList(arium, 'routers', Array.from(routersById.values()));

    // 6. Workflow start, edges & end (edges is required by the runtime, even when empty)
    const workflowEdges = buildWorkflowEdges(nodes, edges, routersById, ctx);
    const existingWorkflow = (isPlainObject(arium.workflow) ? arium.workflow : {}) as AriumWorkflowConfig;
    const start = resolveWorkflowStart(nodes, edges, existingWorkflow.start, workflowEdges, ctx);
    const workflow: Data = { ...existingWorkflow };
    setOrDelete(workflow, 'start', start);
    workflow.edges = workflowEdges;
    workflow.end = buildWorkflowEnds(nodes, workflowEdges, start, ctx);
    arium.workflow = workflow;

    // lineWidth -1: never fold long prompts; noRefs: shared values are written out instead of as YAML anchors
    return { ok: true, yaml: yaml.dump(doc, { lineWidth: -1, noRefs: true }), issues: ctx.issues };
  } catch (e) {
    return { ok: false, error: describeYamlError(e) };
  }
};
