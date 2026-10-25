import yaml from 'js-yaml';
import { Node, Edge, MarkerType } from '@xyflow/react';
import { EDGE_KINDS, NODE_TYPES } from '@app/constants/workflow-builder';
import {
  AriumAgentConfig,
  AriumDoc,
  AriumFunctionNodeConfig,
  AriumIteratorConfig,
  AriumRouterConfig,
  AriumSubworkflowConfig,
  AriumWorkflowConfig,
  AriumWorkflowEdge,
  ParseGraphResult,
} from '@app/types/workflow-builder';
import { getLayoutedElements } from './autoLayout';
import {
  TRIGGER_NODE_ID,
  END_SENTINEL,
  INPUT_SENTINEL,
  MISSING_ARIUM_ERROR,
  isPlainObject,
  hasOwn,
  unique,
  toNameList,
  toStringRecord,
  toBool,
  describeYamlError,
  validateAriumShape,
  isWorkflowReference,
  subworkflowNodeName,
  getAgentConfigMethod,
} from './yaml-shared';

// YAML → canvas graph

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
    labelBgStyle: { fill: 'var(--card)', stroke: '#6366f1', strokeWidth: 1 },
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
    labelBgStyle: { fill: 'var(--card)', stroke: '#818cf8', strokeWidth: 1 },
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
  labelBgStyle: { fill: 'var(--card)', stroke: '#ea580c', strokeWidth: 1 },
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
      labelBgStyle: isFromIterator ? { fill: 'var(--card)', stroke: '#6366f1', strokeWidth: 1 } : undefined,
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
