import yaml from 'js-yaml';
import { Node, Edge, MarkerType } from '@xyflow/react';
import dagre from 'dagre';

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

interface AriumModelConfig {
  provider?: string;
  name?: string;
  [key: string]: unknown;
}

interface AriumSettingsConfig {
  temperature?: number;
  max_tokens?: number;
  allow_early_exit?: boolean;
  context_description?: string;
  fallback_strategy?: string;
  [key: string]: unknown;
}

interface AriumAgentConfig {
  name: string;
  role?: string;
  job?: string;
  prompt?: string;
  act_as?: string;
  yaml_file?: string;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
  tools?: string[];
  input_filter?: string[];
  parser?: unknown;
  [key: string]: unknown;
}

interface AriumFunctionNodeConfig {
  name: string;
  function_name: string;
  description?: string;
  input_filter?: string[];
  prefilled_params?: unknown;
  [key: string]: unknown;
}

interface AriumIteratorConfig {
  name: string;
  execute_node?: string;
  input_filter?: string[];
  forward_all_results?: boolean;
  [key: string]: unknown;
}

interface AriumSubworkflowConfig {
  name: string;
  yaml_file?: string;
  inherit_variables?: boolean;
  input_filter?: string[];
  [key: string]: unknown;
}

interface AriumRouterConfig {
  name: string;
  type?: string;
  strategy?: string;
  field?: string;
  flow_pattern?: string[] | string;
  routing_options?: Record<string, string>;
  routes?: Record<string, string>;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
  [key: string]: unknown;
}

interface AriumWorkflowEdge {
  from: string;
  to: string | string[];
  router?: string;
}

interface AriumWorkflowConfig {
  start?: string;
  edges?: AriumWorkflowEdge[];
  end?: string | string[];
}

interface AriumDoc {
  metadata?: Record<string, unknown>;
  arium?: {
    agents?: AriumAgentConfig[];
    routers?: AriumRouterConfig[];
    function_nodes?: AriumFunctionNodeConfig[];
    iterators?: AriumIteratorConfig[];
    foreach_nodes?: AriumIteratorConfig[];
    ariums?: AriumSubworkflowConfig[];
    workflow?: AriumWorkflowConfig;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

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
    agents.forEach((agent: AriumAgentConfig) => {
      nodes.push({
        id: agent.name,
        type: 'agentNode',
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

      // Visual connection for input_filter
      if (agent.input_filter && Array.isArray(agent.input_filter)) {
        agent.input_filter.forEach((dep: string) => {
          if (dep !== 'input') {
            edges.push({
              id: `e-filter-${dep}-${agent.name}`,
              source: dep,
              target: agent.name,
              type: 'smoothstep',
              animated: false,
              style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
              label: 'Filter',
              labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
            });
          }
        });
      }
    });

    // 2. Process Function Nodes
    functionNodes.forEach((fn: AriumFunctionNodeConfig) => {
      nodes.push({
        id: fn.name,
        type: 'functionNode',
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

      if (fn.input_filter && Array.isArray(fn.input_filter)) {
        fn.input_filter.forEach((dep: string) => {
          if (dep !== 'input') {
            edges.push({
              id: `e-filter-${dep}-${fn.name}`,
              source: dep,
              target: fn.name,
              type: 'smoothstep',
              animated: false,
              style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
              label: 'Filter',
              labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
            });
          }
        });
      }
    });

    // 3. Process Iterators / ForEach
    iterators.forEach((it: AriumIteratorConfig) => {
      nodes.push({
        id: it.name,
        type: 'iteratorNode',
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

      if (it.input_filter && Array.isArray(it.input_filter)) {
        it.input_filter.forEach((dep: string) => {
          if (dep !== 'input') {
            edges.push({
              id: `e-filter-${dep}-${it.name}`,
              source: dep,
              target: it.name,
              type: 'smoothstep',
              animated: false,
              style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
              label: 'Filter',
              labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
            });
          }
        });
      }
    });

    // 4. Process Sub-Workflows (Nested Ariums)
    nestedAriums.forEach((arium: AriumSubworkflowConfig) => {
      const ariumRef = arium.yaml_file || arium.name;
      const localName = ariumRef.split('/').pop() || ariumRef;
      nodes.push({
        id: localName,
        type: 'subworkflowNode',
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

      if (arium.input_filter && Array.isArray(arium.input_filter)) {
        arium.input_filter.forEach((dep: string) => {
          if (dep !== 'input') {
            edges.push({
              id: `e-filter-${dep}-${localName}`,
              source: dep,
              target: localName,
              type: 'smoothstep',
              animated: false,
              style: { stroke: '#3b82f6', strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
              label: 'Filter',
              labelStyle: { fill: '#3b82f6', fontSize: 8, opacity: 0.7 },
            });
          }
        });
      }
    });

    // 5. Process Routers (Smart, Field Match, Reflection, Task Classifier, etc.)
    routers.forEach((router: AriumRouterConfig) => {
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

      nodes.push({
        id: router.name,
        type: 'routerNode',
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

    // 6. Connect ForEach Iterator Loops (Forward Item & Return Cycle)
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

    // 7. Add Start Trigger
    if (workflow.start) {
      nodes.push({
        id: 'trigger-start',
        type: 'triggerNode',
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

    // 7. Process Edges from Workflow
    if (workflow.edges) {
      workflow.edges.forEach((edgeObj: AriumWorkflowEdge) => {
        const from = edgeObj.from;
        const toList = Array.isArray(edgeObj.to) ? edgeObj.to : edgeObj.to ? [edgeObj.to] : [];
        const router = edgeObj.router;

        if (router) {
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
            const shortLabel = intentText.length > 25 ? intentText.substring(0, 25) + '...' : intentText;

            edges.push({
              id: `e-${router}-${toItem}`,
              source: router,
              target: toItem,
              type: 'smoothstep',
              label: shortLabel,
              labelStyle: { fill: '#ea580c', fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
              labelBgPadding: [6, 4] as [number, number],
              labelBgBorderRadius: 6,
              labelBgStyle: { fill: 'hsl(var(--card))', stroke: '#ea580c', strokeWidth: 1 },
              style: { stroke: '#f97316', strokeWidth: 2 },
            });
          });
        } else {
          // Direct connect
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
              labelBgStyle: isFromIterator
                ? { fill: 'hsl(var(--card))', stroke: '#6366f1', strokeWidth: 1 }
                : undefined,
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
        }
      });
    }

    // Implicit edges from routing_options that might be missing in workflow.edges
    routers.forEach((router: AriumRouterConfig) => {
      const routerNode = nodes.find((n: Node) => n.id === router.name);
      const opts = (routerNode?.data?.routing_options as Record<string, string>) || router.routing_options || {};
      Object.keys(opts).forEach((targetName) => {
        const edgeId = `e-${router.name}-${targetName}`;
        if (!edges.find((e) => e.id === edgeId)) {
          const intentText = opts[targetName] || `to ${targetName}`;
          const shortLabel = intentText.length > 25 ? intentText.substring(0, 25) + '...' : intentText;

          edges.push({
            id: edgeId,
            source: router.name,
            target: targetName,
            type: 'smoothstep',
            label: shortLabel,
            labelStyle: { fill: '#ea580c', fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
            labelBgPadding: [6, 4] as [number, number],
            labelBgBorderRadius: 6,
            labelBgStyle: { fill: 'hsl(var(--card))', stroke: '#ea580c', strokeWidth: 1 },
            style: { stroke: '#f97316', strokeWidth: 2 },
          });
        }
      });
    });

    return getLayoutedElements(nodes, edges);
  } catch (e) {
    console.error('Error parsing YAML to Graph:', e);
    return { nodes: [], edges: [] };
  }
};

export const serializeGraphToYaml = (nodes: Node[], edges: Edge[], currentYaml: string): string => {
  try {
    const doc = (yaml.load(currentYaml) as AriumDoc) || {};
    if (!doc.arium) doc.arium = {};

    const toTemperature = (v: unknown, fallback: number) => {
      const n = Number(v);
      return v === '' || v === undefined || v === null || Number.isNaN(n) ? fallback : n;
    };

    // 1. Reconstruct Agents
    const existingAgents = doc.arium.agents || [];
    const newAgents = nodes
      .filter((n) => n.type === 'agentNode')
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
        if (n.data.input_filter && Array.isArray(n.data.input_filter) && n.data.input_filter.length > 0) {
          agentObj.input_filter = n.data.input_filter;
        } else {
          delete agentObj.input_filter;
        }
        if (n.data.parser) {
          agentObj.parser = n.data.parser;
        } else {
          delete agentObj.parser;
        }

        delete agentObj.yaml_file; // Force inline configuration for the builder

        return agentObj;
      });
    doc.arium.agents = newAgents.length > 0 ? (newAgents as AriumAgentConfig[]) : undefined;

    // 2. Reconstruct Function Nodes
    const existingFunctions = doc.arium.function_nodes || [];
    const newFunctions = nodes
      .filter((n) => n.type === 'functionNode')
      .map((n) => {
        const existing = (existingFunctions.find((fn: AriumFunctionNodeConfig) => fn.name === n.id) ||
          {}) as Partial<AriumFunctionNodeConfig>;
        const fnObj: Record<string, unknown> = {
          ...existing,
          name: n.data.label || n.id,
          function_name: n.data.function_name || 'passthrough',
          description: n.data.description || undefined,
        };

        if (n.data.input_filter && Array.isArray(n.data.input_filter) && n.data.input_filter.length > 0) {
          fnObj.input_filter = n.data.input_filter;
        } else {
          delete fnObj.input_filter;
        }
        if (n.data.prefilled_params) {
          fnObj.prefilled_params = n.data.prefilled_params;
        } else {
          delete fnObj.prefilled_params;
        }

        return fnObj;
      });
    doc.arium.function_nodes = newFunctions.length > 0 ? (newFunctions as AriumFunctionNodeConfig[]) : undefined;

    // 3. Reconstruct Iterators
    const existingIterators = doc.arium.iterators || doc.arium.foreach_nodes || [];
    const newIterators = nodes
      .filter((n) => n.type === 'iteratorNode')
      .map((n) => {
        const existing = (existingIterators.find((it: AriumIteratorConfig) => it.name === n.id) ||
          {}) as Partial<AriumIteratorConfig>;
        const itObj: Record<string, unknown> = {
          ...existing,
          name: n.data.label || n.id,
          execute_node: n.data.execute_node || '',
          forward_all_results: !!n.data.forward_all_results,
        };

        if (n.data.input_filter && Array.isArray(n.data.input_filter) && n.data.input_filter.length > 0) {
          itObj.input_filter = n.data.input_filter;
        } else {
          delete itObj.input_filter;
        }

        return itObj;
      });
    doc.arium.iterators = newIterators.length > 0 ? (newIterators as AriumIteratorConfig[]) : undefined;
    delete doc.arium.foreach_nodes; // normalize to iterators

    // 4. Reconstruct Sub-Workflows (Ariums)
    const existingAriums = doc.arium.ariums || [];
    const newAriums = nodes
      .filter((n) => n.type === 'subworkflowNode')
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

        if (n.data.input_filter && Array.isArray(n.data.input_filter) && n.data.input_filter.length > 0) {
          ariumObj.input_filter = n.data.input_filter;
        } else {
          delete ariumObj.input_filter;
        }

        return ariumObj;
      });
    doc.arium.ariums = newAriums.length > 0 ? (newAriums as AriumSubworkflowConfig[]) : undefined;

    // 5. Reconstruct Routers
    const existingRouters = doc.arium.routers || [];
    const newRouters = nodes
      .filter((n) => n.type === 'routerNode')
      .map((n) => {
        const existing = (existingRouters.find((r: AriumRouterConfig) => r.name === n.id) ||
          {}) as Partial<AriumRouterConfig>;
        const strategy = (n.data.strategy || n.data.type || 'smart') as string;
        const isFieldMatch = strategy === 'field_match';
        const isReflection = strategy === 'reflection';

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
          const newModel: Record<string, unknown> = { ...existing.model };
          delete newModel.name;
          delete newModel.model_id;
          newModel.provider = n.data.provider || 'openai';
          if (n.data.provider === 'rootflo') {
            newModel.model_id = n.data.model_id || n.data.model || '';
          } else {
            newModel.name = n.data.model || 'gpt-4o-mini';
          }
          routerObj.model = newModel;
          routerObj.settings = {
            ...existing.settings,
            temperature: toTemperature(n.data.temperature, 0.3),
            allow_early_exit: !!n.data.allow_early_exit,
          };
          delete routerObj.field;
        } else {
          // Smart or general LLM router
          const newModel: Record<string, unknown> = { ...existing.model };
          delete newModel.name;
          delete newModel.model_id;
          newModel.provider = n.data.provider || 'openai';
          if (n.data.provider === 'rootflo') {
            newModel.model_id = n.data.model_id || n.data.model || '';
          } else {
            newModel.name = n.data.model || 'gpt-4o-mini';
          }
          routerObj.model = newModel;
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
    doc.arium.routers = newRouters.length > 0 ? (newRouters as AriumRouterConfig[]) : undefined;

    // 6. Reconstruct Workflow Start, Edges & End
    const workflow: Record<string, unknown> = {};
    const startEdge = edges.find((e) => e.source === 'trigger-start');
    if (startEdge) {
      workflow.start = startEdge.target;
    } else if (doc.arium.workflow?.start) {
      workflow.start = doc.arium.workflow.start;
    } else if (newAgents.length > 0) {
      workflow.start = (newAgents[0] as { name: string }).name;
    }

    const workflowEdges: Array<Record<string, unknown>> = [];
    const validExecutableTypes = ['agentNode', 'functionNode', 'iteratorNode', 'subworkflowNode', 'routerNode'];
    const validExecutableNodes = nodes.filter((n) => validExecutableTypes.includes(n.type || ''));
    const validSources = nodes
      .filter((n) => ['agentNode', 'functionNode', 'iteratorNode', 'subworkflowNode'].includes(n.type || ''))
      .map((n) => n.id);

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
            validExecutableNodes.some((n) => n.id === e.target && n.type !== 'routerNode')
        )
        .map((e) => e.target);

      // Router targets
      const routerEdges = edges.filter(
        (e) =>
          e.source === sourceId &&
          !e.id.startsWith('e-filter-') &&
          nodes.find((n) => n.id === e.target)?.type === 'routerNode'
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

    if (workflowEdges.length > 0) {
      workflow.edges = workflowEdges;
    }

    // 7. Calculate and assign Terminal Nodes for workflow.end
    const executableNodeIds = validExecutableNodes.map((n) => n.id);
    const nodesWithOutgoing = new Set<string>();
    workflowEdges.forEach((edgeObj) => {
      if (edgeObj.from) nodesWithOutgoing.add(edgeObj.from as string);
      if (edgeObj.router) nodesWithOutgoing.add(edgeObj.router as string);
    });

    const computedTerminals = executableNodeIds.filter((id) => !nodesWithOutgoing.has(id));

    // Preserve existing ends if they still exist in the graph, otherwise use computed terminals
    const prevEnds = Array.isArray(doc.arium.workflow?.end)
      ? doc.arium.workflow.end
      : doc.arium.workflow?.end
        ? [doc.arium.workflow.end]
        : [];
    const validPrevEnds = prevEnds.filter((id: string) => executableNodeIds.includes(id));

    const combinedEnds = Array.from(new Set([...validPrevEnds, ...computedTerminals]));

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
