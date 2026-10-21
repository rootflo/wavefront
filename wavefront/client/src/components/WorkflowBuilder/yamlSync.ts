import yaml from 'js-yaml';
import { Node, Edge, MarkerType } from '@xyflow/react';
import dagre from 'dagre';
import { NODE_TYPES } from '@app/constants/workflow-builder';
import {
  AriumAgentConfig,
  AriumDoc,
  AriumFunctionNodeConfig,
  AriumIteratorConfig,
  AriumModelConfig,
  AriumRouterConfig,
  AriumSubworkflowConfig,
  AriumWorkflowConfig,
  AriumWorkflowEdge,
} from '@app/types/workflow-builder';

const nodeWidth = 320;
const nodeHeight = 180;

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
    if (edge.id.startsWith('e-filter-') || edge.id.startsWith('e-reflect-') || edge.id.startsWith('e-loop-return-')) {
      return;
    }
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      dagreGraph.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    if (nodeWithPosition) {
      node.position = {
        x: Math.round(nodeWithPosition.x - nodeWidth / 2),
        y: Math.round(nodeWithPosition.y - nodeHeight / 2),
      };
    }
  });

  return { nodes, edges };
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
  },
];

// Visual connection for input_filter (dashed "Filter" edges from each dependency to the node)
const buildFilterEdges = (inputFilter: string[] | undefined, targetId: string): Edge[] => {
  const filterEdges: Edge[] = [];
  if (inputFilter && Array.isArray(inputFilter)) {
    inputFilter.forEach((dep: string) => {
      if (dep !== 'input') {
        filterEdges.push({
          id: `e-filter-${dep}-${targetId}`,
          source: dep,
          target: targetId,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
          label: 'Filter',
          labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
        });
      }
    });
  }
  return filterEdges;
};

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
});

const processAgents = (
  agents: AriumAgentConfig[],
  workflow: AriumWorkflowConfig,
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  agents.forEach((agent: AriumAgentConfig) => {
    nodes.push({
      id: agent.name,
      type: NODE_TYPES.AGENT,
      position: { x: 0, y: 0 },
      data: {
        label: agent.name,
        role: agent.role || '',
        job: agent.job || agent.prompt || '',
        act_as: agent.act_as,
        yaml_file: agent.yaml_file,
        provider: agent.model?.provider || 'rootflo',
        model: agent.model?.name || '',
        model_id: (agent.model as Record<string, unknown>)?.model_id || '',
        temperature: agent.settings?.temperature ?? 0.7,
        max_tokens: agent.settings?.max_tokens,
        tools: agent.tools || [],
        input_filter: agent.input_filter,
        parser: agent.parser,
        isStartNode: workflow.start === agent.name,
        isEndNode: endNodes.includes(agent.name),
        type: 'agent',
      },
    });

    edges.push(...buildFilterEdges(agent.input_filter, agent.name));
  });
};

const processFunctionNodes = (
  functionNodes: AriumFunctionNodeConfig[],
  workflow: AriumWorkflowConfig,
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
        isStartNode: workflow.start === fn.name,
        isEndNode: endNodes.includes(fn.name),
        type: 'function',
      },
    });

    edges.push(...buildFilterEdges(fn.input_filter, fn.name));
  });
};

const processIterators = (
  iterators: AriumIteratorConfig[],
  workflow: AriumWorkflowConfig,
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  iterators.forEach((it: AriumIteratorConfig) => {
    nodes.push({
      id: it.name,
      type: NODE_TYPES.ITERATOR,
      position: { x: 0, y: 0 },
      data: {
        label: it.name,
        execute_node: it.execute_node,
        input_filter: it.input_filter,
        forward_all_results: !!it.forward_all_results,
        isStartNode: workflow.start === it.name,
        isEndNode: endNodes.includes(it.name),
        type: 'iterator',
      },
    });

    edges.push(...buildFilterEdges(it.input_filter, it.name));
  });
};

const processSubworkflows = (
  nestedAriums: AriumSubworkflowConfig[],
  workflow: AriumWorkflowConfig,
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  nestedAriums.forEach((arium: AriumSubworkflowConfig) => {
    const ariumRef = arium.yaml_file || arium.name;
    const localName = ariumRef.split('/').pop() || ariumRef;
    nodes.push({
      id: localName,
      type: NODE_TYPES.SUBWORKFLOW,
      position: { x: 0, y: 0 },
      data: {
        label: localName,
        name: localName,
        yaml_file: ariumRef,
        inherit_variables: arium.inherit_variables !== false,
        input_filter: arium.input_filter,
        isStartNode: workflow.start === localName,
        isEndNode: endNodes.includes(localName),
        type: 'subworkflow',
      },
    });

    edges.push(...buildFilterEdges(arium.input_filter, localName));
  });
};

// Merge `routes` (match value -> target) into `routing_options` (target -> intent text)
const buildRoutingOptions = (router: AriumRouterConfig): Record<string, string> => {
  const routingOpts: Record<string, string> = { ...(router.routing_options || {}) };
  if (router.routes && typeof router.routes === 'object') {
    Object.entries(router.routes).forEach(([matchVal, targetNode]) => {
      if (typeof targetNode === 'string') {
        const shortTarget = targetNode.split('/').pop() || targetNode;
        if (!routingOpts[shortTarget]) {
          routingOpts[shortTarget] = matchVal;
        } else if (!routingOpts[shortTarget].includes(matchVal)) {
          routingOpts[shortTarget] += ` | ${matchVal}`;
        }
      }
    });
  }
  return routingOpts;
};

// Process Routers (Smart, Field Match, Reflection, Task Classifier, etc.)
const processRouters = (
  routers: AriumRouterConfig[],
  workflow: AriumWorkflowConfig,
  endNodes: string[],
  nodes: Node[],
  edges: Edge[]
) => {
  routers.forEach((router: AriumRouterConfig) => {
    const routingOpts = buildRoutingOptions(router);

    nodes.push({
      id: router.name,
      type: NODE_TYPES.ROUTER,
      position: { x: 0, y: 0 },
      data: {
        label: router.name,
        strategy: router.type || 'smart',
        type: router.type || 'smart',
        field: router.field,
        flow_pattern: router.flow_pattern,
        allow_early_exit: router.settings?.allow_early_exit,
        provider: router.model?.provider || '',
        model: router.model?.name || '',
        model_id: (router.model as Record<string, unknown>)?.model_id || '',
        temperature: router.settings?.temperature ?? 0.3,
        context_description: router.settings?.context_description || '',
        fallback_strategy: router.settings?.fallback_strategy || 'first',
        routing_options: routingOpts,
        isStartNode: workflow.start === router.name,
        isEndNode: endNodes.includes(router.name),
      },
    });

    // Reflection flow visual loops
    if (router.type === 'reflection' && Array.isArray(router.flow_pattern) && router.flow_pattern.length > 1) {
      for (let i = 0; i < router.flow_pattern.length - 1; i++) {
        const from = router.flow_pattern[i];
        const to = router.flow_pattern[i + 1];
        const edgeId = `e-reflect-${router.name}-${from}-${to}-${i}`;
        edges.push({
          id: edgeId,
          source: from,
          target: to,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#f43f5e', strokeWidth: 1.5, strokeDasharray: '5,5' },
          label: `Loop #${i + 1}`,
          labelStyle: { fill: '#f43f5e', fontSize: 9 },
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
      id: 'trigger-start',
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
      source: 'trigger-start',
      target: workflow.start,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#a855f7', strokeWidth: 2 },
    });
  }
};

// Connect from -> router, then router -> each target (mutates the router node's routing_options)
const addRouterEdges = (from: string, router: string, toList: string[], nodes: Node[], edges: Edge[]) => {
  // Connect from -> router
  edges.push({
    id: `e-${from}-${router}`,
    source: from,
    target: router,
    type: 'smoothstep',
    animated: true,
    style: { stroke: '#64748b', strokeWidth: 2 },
  });

  // Connect router -> to
  const routerData = nodes.find((n: Node) => n.id === router);
  const routerOpts = (routerData?.data?.routing_options as Record<string, string>) || {};

  toList.forEach((toItem: string) => {
    if (!routerOpts[toItem]) {
      routerOpts[toItem] = `Route to ${toItem}`;
      if (routerData && routerData.data) {
        routerData.data.routing_options = routerOpts;
      }
    }
    const intentText = routerOpts[toItem];
    const shortLabel = truncateLabel(intentText);

    edges.push(createRouterRouteEdge(router, toItem, shortLabel));
  });
};

// Direct connect from -> each target
const addDirectEdges = (from: string, toList: string[], iterators: AriumIteratorConfig[], edges: Edge[]) => {
  toList.forEach((toItem: string) => {
    const isFromIterator = iterators.some((it: AriumIteratorConfig) => it.name === from);
    edges.push({
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
  if (workflow.edges) {
    workflow.edges.forEach((edgeObj: AriumWorkflowEdge) => {
      const from = edgeObj.from;
      const toList = Array.isArray(edgeObj.to) ? edgeObj.to : edgeObj.to ? [edgeObj.to] : [];
      const router = edgeObj.router;

      if (router) {
        addRouterEdges(from, router, toList, nodes, edges);
      } else {
        addDirectEdges(from, toList, iterators, edges);
      }
    });
  }
};

// Implicit edges from routing_options that might be missing in workflow.edges
const addImplicitRouterEdges = (routers: AriumRouterConfig[], nodes: Node[], edges: Edge[]) => {
  routers.forEach((router: AriumRouterConfig) => {
    const routerNode = nodes.find((n: Node) => n.id === router.name);
    const opts = (routerNode?.data?.routing_options as Record<string, string>) || router.routing_options || {};
    Object.keys(opts).forEach((targetName) => {
      const edgeId = `e-${router.name}-${targetName}`;
      if (!edges.find((e) => e.id === edgeId)) {
        const intentText = opts[targetName] || `to ${targetName}`;
        const shortLabel = truncateLabel(intentText);

        edges.push(createRouterRouteEdge(router.name, targetName, shortLabel));
      }
    });
  });
};

export const parseYamlToGraph = (yamlString: string): { nodes: Node[]; edges: Edge[] } => {
  try {
    const doc = yaml.load(yamlString) as AriumDoc | null;
    if (!doc || !doc.arium) return { nodes: [], edges: [] };

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    const agents = doc.arium.agents || [];
    const routers = doc.arium.routers || [];
    const functionNodes = doc.arium.function_nodes || [];
    const iterators = doc.arium.iterators || doc.arium.foreach_nodes || [];
    const nestedAriums = doc.arium.ariums || [];
    const workflow = doc.arium.workflow || { edges: [] };
    const endNodes = Array.isArray(workflow.end) ? workflow.end : workflow.end ? [workflow.end] : [];

    // 1. Process Agents
    processAgents(agents, workflow, endNodes, nodes, edges);

    // 2. Process Function Nodes
    processFunctionNodes(functionNodes, workflow, endNodes, nodes, edges);

    // 3. Process Iterators / ForEach
    processIterators(iterators, workflow, endNodes, nodes, edges);

    // 4. Process Sub-Workflows (Nested Ariums)
    processSubworkflows(nestedAriums, workflow, endNodes, nodes, edges);

    // 5. Process Routers (Smart, Field Match, Reflection, Task Classifier, etc.)
    processRouters(routers, workflow, endNodes, nodes, edges);

    // 6. Connect ForEach Iterator Loops (Forward Item & Return Cycle)
    connectIteratorLoops(iterators, nodes, edges);

    // 7. Add Start Trigger
    addStartTrigger(workflow, nodes, edges);

    // 8. Process Edges from Workflow
    processWorkflowEdges(workflow, iterators, nodes, edges);

    // Implicit edges from routing_options that might be missing in workflow.edges
    addImplicitRouterEdges(routers, nodes, edges);

    return getLayoutedElements(nodes, edges);
  } catch (e) {
    console.error('Error parsing YAML to Graph:', e);
    return { nodes: [], edges: [] };
  }
};

const toTemperature = (v: unknown, fallback: number) => {
  const n = Number(v);
  return v === '' || v === undefined || v === null || Number.isNaN(n) ? fallback : n;
};

// Node types that take part in the workflow execution graph
const EXECUTABLE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
  NODE_TYPES.ROUTER,
];
// Executable node types that can be the `from` of a workflow edge (everything except routers)
const SOURCE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
];

// Keep input_filter only when it is a non-empty array
const applyInputFilter = (obj: Record<string, unknown>, data: Node['data']) => {
  if (data.input_filter && Array.isArray(data.input_filter) && data.input_filter.length > 0) {
    obj.input_filter = data.input_filter;
  } else {
    delete obj.input_filter;
  }
};

// Reconstruct Agents
const serializeAgents = (nodes: Node[], existingAgents: AriumAgentConfig[]) =>
  nodes
    .filter((n) => n.type === NODE_TYPES.AGENT)
    .map((n) => {
      const existing = (existingAgents.find((a: AriumAgentConfig) => a.name === n.id) ||
        {}) as Partial<AriumAgentConfig>;

      const agentObj: Record<string, unknown> = {
        ...existing,
        name: n.data.label || n.id,
        role: n.data.role || undefined,
        job: n.data.job || undefined,
        act_as: n.data.act_as || undefined,
        model: {
          ...existing.model,
          name: undefined,
          provider: 'rootflo',
          model_id: n.data.model_id || n.data.model || '',
        },
        settings: {
          ...existing.settings,
          temperature: toTemperature(n.data.temperature, 0.7),
        },
      };

      if (n.data.max_tokens) {
        (agentObj.settings as Record<string, unknown>).max_tokens = Number(n.data.max_tokens);
      }
      if (n.data.tools && Array.isArray(n.data.tools) && n.data.tools.length > 0) {
        agentObj.tools = n.data.tools;
      } else {
        delete agentObj.tools;
      }
      applyInputFilter(agentObj, n.data);
      if (n.data.parser) {
        agentObj.parser = n.data.parser;
      } else {
        delete agentObj.parser;
      }

      delete agentObj.yaml_file; // Force inline configuration for the builder

      return agentObj;
    });

// Reconstruct Function Nodes
const serializeFunctionNodes = (nodes: Node[], existingFunctions: AriumFunctionNodeConfig[]) =>
  nodes
    .filter((n) => n.type === NODE_TYPES.FUNCTION)
    .map((n) => {
      const existing = (existingFunctions.find((fn: AriumFunctionNodeConfig) => fn.name === n.id) ||
        {}) as Partial<AriumFunctionNodeConfig>;
      const fnObj: Record<string, unknown> = {
        ...existing,
        name: n.data.label || n.id,
        function_name: n.data.function_name || 'passthrough',
        description: n.data.description || undefined,
      };

      applyInputFilter(fnObj, n.data);
      if (n.data.prefilled_params) {
        fnObj.prefilled_params = n.data.prefilled_params;
      } else {
        delete fnObj.prefilled_params;
      }

      return fnObj;
    });

// Reconstruct Iterators
const serializeIterators = (nodes: Node[], existingIterators: AriumIteratorConfig[]) =>
  nodes
    .filter((n) => n.type === NODE_TYPES.ITERATOR)
    .map((n) => {
      const existing = (existingIterators.find((it: AriumIteratorConfig) => it.name === n.id) ||
        {}) as Partial<AriumIteratorConfig>;
      const itObj: Record<string, unknown> = {
        ...existing,
        name: n.data.label || n.id,
        execute_node: n.data.execute_node || '',
        forward_all_results: !!n.data.forward_all_results,
      };

      applyInputFilter(itObj, n.data);

      return itObj;
    });

// Reconstruct Sub-Workflows (Ariums)
const serializeSubworkflows = (nodes: Node[], existingAriums: AriumSubworkflowConfig[]) =>
  nodes
    .filter((n) => n.type === NODE_TYPES.SUBWORKFLOW)
    .map((n) => {
      const fullRef = (n.data.yaml_file || n.data.ref || n.data.label || n.id) as string;
      const existing = (existingAriums.find(
        (a: AriumSubworkflowConfig) => a.name === n.id || a.yaml_file === fullRef
      ) || {}) as Partial<AriumSubworkflowConfig>;

      const ariumObj: Record<string, unknown> = {
        ...existing,
        name: n.id,
        inherit_variables: n.data.inherit_variables !== false,
      };

      if (fullRef && fullRef !== n.id) {
        ariumObj.yaml_file = fullRef;
      } else {
        delete ariumObj.yaml_file;
      }

      applyInputFilter(ariumObj, n.data);

      return ariumObj;
    });

// Build the model block for LLM routers (reflection / smart); rootflo uses model_id, others use name
const buildRouterModel = (existingModel: AriumModelConfig | undefined, data: Node['data']) => {
  const newModel: Record<string, unknown> = { ...existingModel };
  delete newModel.name;
  delete newModel.model_id;
  newModel.provider = data.provider || 'openai';
  if (data.provider === 'rootflo') {
    newModel.model_id = data.model_id || data.model || '';
  } else {
    newModel.name = data.model || 'gpt-4o-mini';
  }
  return newModel;
};

// Derive routing_options from the node data/existing config plus the router's outgoing edges
const buildSerializedRoutingOptions = (
  n: Node,
  existing: Partial<AriumRouterConfig>,
  edges: Edge[],
  isFieldMatch: boolean
) => {
  const outgoingEdges = edges.filter((e) => e.source === n.id && !e.id.startsWith('e-reflect-'));
  const routingOptions = {
    ...((n.data.routing_options as Record<string, string>) || existing.routing_options || {}),
  };
  outgoingEdges.forEach((edge) => {
    if (!routingOptions[edge.target]) {
      routingOptions[edge.target] = isFieldMatch ? edge.target : `Route to ${edge.target}`;
    }
  });
  // Clean up orphaned routing options if edge is removed visually
  Object.keys(routingOptions).forEach((k) => {
    if (
      !outgoingEdges.find((e) => e.target === k) &&
      (routingOptions[k] === `Route to ${k}` || routingOptions[k] === k)
    ) {
      delete routingOptions[k];
    }
  });
  return routingOptions;
};

// Reconstruct Routers
const serializeRouters = (nodes: Node[], edges: Edge[], existingRouters: AriumRouterConfig[]) =>
  nodes
    .filter((n) => n.type === NODE_TYPES.ROUTER)
    .map((n) => {
      const existing = (existingRouters.find((r: AriumRouterConfig) => r.name === n.id) ||
        {}) as Partial<AriumRouterConfig>;
      const strategy = (n.data.strategy || n.data.type || 'smart') as string;
      const isFieldMatch = strategy === 'field_match';
      const isReflection = strategy === 'reflection';

      const routingOptions = buildSerializedRoutingOptions(n, existing, edges, isFieldMatch);

      const routerObj: Record<string, unknown> = {
        ...existing,
        name: n.data.label || n.id,
        type: strategy,
        routing_options: Object.keys(routingOptions).length > 0 ? routingOptions : undefined,
      };

      if (isFieldMatch) {
        routerObj.field = n.data.field || 'doc_type';
        delete routerObj.model;
        delete routerObj.settings;
        delete routerObj.flow_pattern;
      } else if (isReflection) {
        routerObj.flow_pattern = Array.isArray(n.data.flow_pattern)
          ? n.data.flow_pattern
          : n.data.flow_pattern
            ? [n.data.flow_pattern]
            : [];
        routerObj.model = buildRouterModel(existing.model, n.data);
        routerObj.settings = {
          ...existing.settings,
          temperature: toTemperature(n.data.temperature, 0.3),
          allow_early_exit: !!n.data.allow_early_exit,
        };
        delete routerObj.field;
      } else {
        // Smart or general LLM router
        routerObj.model = buildRouterModel(existing.model, n.data);
        routerObj.settings = {
          ...existing.settings,
          temperature: toTemperature(n.data.temperature, 0.3),
          context_description: n.data.context_description || undefined,
          fallback_strategy: n.data.fallback_strategy || 'first',
        };
        delete routerObj.field;
        delete routerObj.flow_pattern;
      }

      return routerObj;
    });

// Resolve workflow.start: trigger edge first, then the existing start, then the first agent
const resolveWorkflowStart = (
  edges: Edge[],
  existingWorkflow: AriumWorkflowConfig | undefined,
  newAgents: Array<Record<string, unknown>>
): string | undefined => {
  const startEdge = edges.find((e) => e.source === 'trigger-start');
  if (startEdge) {
    return startEdge.target;
  } else if (existingWorkflow?.start) {
    return existingWorkflow.start;
  } else if (newAgents.length > 0) {
    return (newAgents[0] as { name: string }).name;
  }
  return undefined;
};

// Build workflow.edges from the visual edges (direct targets and router targets per source node)
const buildWorkflowEdges = (
  nodes: Node[],
  edges: Edge[],
  validExecutableNodes: Node[],
  newRouters: Array<Record<string, unknown>>
) => {
  const workflowEdges: Array<Record<string, unknown>> = [];
  const validSources = nodes.filter((n) => SOURCE_NODE_TYPES.includes(n.type || '')).map((n) => n.id);

  validSources.forEach((sourceId) => {
    // Direct targets (excluding filter and execution visual edges)
    const directTargets = edges
      .filter(
        (e) =>
          e.source === sourceId &&
          !e.id.startsWith('e-filter-') &&
          !e.id.startsWith('e-exec-') &&
          !e.id.startsWith('e-loop-') &&
          !e.id.startsWith('e-reflect-') &&
          validExecutableNodes.some((n) => n.id === e.target && n.type !== NODE_TYPES.ROUTER)
      )
      .map((e) => e.target);

    // Router targets
    const routerEdges = edges.filter(
      (e) =>
        e.source === sourceId &&
        !e.id.startsWith('e-filter-') &&
        nodes.find((n) => n.id === e.target)?.type === NODE_TYPES.ROUTER
    );

    if (directTargets.length > 0 && sourceId !== 'trigger-start') {
      workflowEdges.push({
        from: sourceId,
        to: directTargets,
      });
    }

    routerEdges.forEach((re) => {
      const routerId = re.target;
      const routerTargets = Array.from(
        new Set([
          ...edges.filter((e) => e.source === routerId && !e.id.startsWith('e-reflect-')).map((e) => e.target),
          ...Object.keys(newRouters.find((r) => r.name === routerId)?.routing_options || {}),
        ])
      );

      if (routerTargets.length > 0 && sourceId !== 'trigger-start') {
        workflowEdges.push({
          from: sourceId,
          router: routerId,
          to: routerTargets,
        });
      }
    });
  });

  return workflowEdges;
};

// Calculate Terminal Nodes for workflow.end
const buildWorkflowEnds = (
  validExecutableNodes: Node[],
  workflowEdges: Array<Record<string, unknown>>,
  existingWorkflow: AriumWorkflowConfig | undefined
): string[] => {
  const executableNodeIds = validExecutableNodes.map((n) => n.id);
  const nodesWithOutgoing = new Set<string>();
  workflowEdges.forEach((edgeObj) => {
    if (edgeObj.from) nodesWithOutgoing.add(edgeObj.from as string);
    if (edgeObj.router) nodesWithOutgoing.add(edgeObj.router as string);
  });

  const computedTerminals = executableNodeIds.filter((id) => !nodesWithOutgoing.has(id));

  // Preserve existing ends if they still exist in the graph, otherwise use computed terminals
  const existingEnd = existingWorkflow?.end;
  const prevEnds = Array.isArray(existingEnd) ? existingEnd : existingEnd ? [existingEnd] : [];
  const validPrevEnds = prevEnds.filter((id: string) => executableNodeIds.includes(id));

  return Array.from(new Set([...validPrevEnds, ...computedTerminals]));
};

export const serializeGraphToYaml = (nodes: Node[], edges: Edge[], currentYaml: string): string => {
  try {
    const doc = (yaml.load(currentYaml) as AriumDoc) || {};
    if (!doc.arium) doc.arium = {};

    // 1. Reconstruct Agents
    const newAgents = serializeAgents(nodes, doc.arium.agents || []);
    doc.arium.agents = newAgents.length > 0 ? (newAgents as AriumAgentConfig[]) : undefined;

    // 2. Reconstruct Function Nodes
    const newFunctions = serializeFunctionNodes(nodes, doc.arium.function_nodes || []);
    doc.arium.function_nodes = newFunctions.length > 0 ? (newFunctions as AriumFunctionNodeConfig[]) : undefined;

    // 3. Reconstruct Iterators
    const newIterators = serializeIterators(nodes, doc.arium.iterators || doc.arium.foreach_nodes || []);
    doc.arium.iterators = newIterators.length > 0 ? (newIterators as AriumIteratorConfig[]) : undefined;
    delete doc.arium.foreach_nodes; // normalize to iterators

    // 4. Reconstruct Sub-Workflows (Ariums)
    const newAriums = serializeSubworkflows(nodes, doc.arium.ariums || []);
    doc.arium.ariums = newAriums.length > 0 ? (newAriums as AriumSubworkflowConfig[]) : undefined;

    // 5. Reconstruct Routers
    const newRouters = serializeRouters(nodes, edges, doc.arium.routers || []);
    doc.arium.routers = newRouters.length > 0 ? (newRouters as AriumRouterConfig[]) : undefined;

    // 6. Reconstruct Workflow Start, Edges & End
    const workflow: Record<string, unknown> = {};
    const start = resolveWorkflowStart(edges, doc.arium.workflow, newAgents);
    if (start !== undefined) {
      workflow.start = start;
    }

    const validExecutableNodes = nodes.filter((n) => EXECUTABLE_NODE_TYPES.includes(n.type || ''));
    const workflowEdges = buildWorkflowEdges(nodes, edges, validExecutableNodes, newRouters);
    if (workflowEdges.length > 0) {
      workflow.edges = workflowEdges;
    }

    // 7. Calculate and assign Terminal Nodes for workflow.end
    const combinedEnds = buildWorkflowEnds(validExecutableNodes, workflowEdges, doc.arium.workflow);
    if (combinedEnds.length > 0) {
      workflow.end = combinedEnds;
    }

    doc.arium.workflow = Object.keys(workflow).length > 0 ? workflow : undefined;

    return yaml.dump(doc);
  } catch (e) {
    console.error('Error serializing Graph to YAML:', e);
    return currentYaml;
  }
};
