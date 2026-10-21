import { Connection, Edge, MarkerType, Node, XYPosition } from '@xyflow/react';
import { EDGE_KINDS, EdgeKind, NODE_TYPES, getEdgeKind } from '@app/constants/workflow-builder';
import { createIteratorLoopEdges, getLayoutedElements } from './yamlSync';

// Pure graph-transform layer for the visual workflow editor.
// Every structural edit goes through applyGraphAction, which returns new node/edge objects (never mutates its input)
// and returns the same graph object when nothing changed.

export interface Graph {
  nodes: Node[];
  edges: Edge[];
}

export const TRIGGER_NODE_ID = 'trigger-start';

// Handle ids used by iterator loops (see IteratorNode and the loop-target handle on every node)
export const LOOP_OUT_HANDLE = 'loop-out';
export const LOOP_BACK_HANDLE = 'loop-back';
export const LOOP_RETURN_HANDLE = 'loop-return';

const START_EDGE_COLOR = '#a855f7';
const FLOW_EDGE_COLOR = '#64748b';
const ITERATOR_EDGE_COLOR = '#6366f1';
const ROUTER_EDGE_COLOR = '#f97316';
const FILTER_EDGE_COLOR = '#3b82f6';
const ROUTE_LABEL_MAX_LENGTH = 25;
const NEW_NODE_OFFSET_X = 360;

type RoutingOptions = Record<string, string>;

const hasOwn = (obj: object, key: string) => Object.prototype.hasOwnProperty.call(obj, key);

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const getRoutingOptions = (node: Node): RoutingOptions =>
  isPlainObject(node.data?.routing_options) ? (node.data.routing_options as RoutingOptions) : {};

// Router strategy (flo_ai router `type`). `strategy` is authoritative; `type` is only read for nodes parsed before
// the two were kept in sync.
export const getRouterStrategy = (data: Record<string, unknown> | undefined): string =>
  (data?.strategy as string) || (data?.type as string) || 'smart';

// ---------------------------------------------------------------------------
// Node classification and naming
// ---------------------------------------------------------------------------

// Node types flo_ai can resolve by name (workflow.start, edge targets, execute_node, input_filter).
// Routers are not nodes at runtime: they only exist on edges.
const EXECUTABLE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
];

export const isExecutableNode = (node?: Node): boolean => !!node && EXECUTABLE_NODE_TYPES.includes(node.type ?? '');

// Inline node names: identifier-like, so they can never collide with edge-id separators or stored-agent references ('/')
const NODE_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;

// 'end' is the terminal sentinel in workflow edges, 'input' is the user-input sentinel in input_filter,
// and the trigger id belongs to the canvas
const RESERVED_NODE_NAMES = ['end', 'input', TRIGGER_NODE_ID];

export const sanitizeNodeName = (raw: string): string => raw.trim().replace(/\s+/g, '_');

// Returns a user-facing error, or null when `name` can be used for the node `selfId`
export const validateNodeName = (name: string, nodes: Node[], selfId?: string): string | null => {
  if (!name) return 'Name is required.';
  if (RESERVED_NODE_NAMES.includes(name)) return `'${name}' is reserved by the workflow runtime.`;
  if (!NODE_NAME_PATTERN.test(name)) {
    return 'Use letters, digits and underscores only, starting with a letter or underscore (max 64).';
  }
  if (nodes.some((n) => n.id === name && n.id !== selfId)) return `A step named '${name}' already exists.`;
  return null;
};

export const nextNodeId = (prefix: string, nodes: Node[]): string => {
  const ids = new Set(nodes.map((n) => n.id));
  let i = 1;
  while (ids.has(`${prefix}_${i}`)) i++;
  return `${prefix}_${i}`;
};

// Default position for a node added without a drop point: to the right of the right-most step
export const nextNodePosition = (nodes: Node[]): XYPosition => {
  const steps = nodes.filter((n) => n.type !== NODE_TYPES.TRIGGER);
  if (steps.length === 0) return { x: 250, y: 150 };
  const rightMost = steps.reduce((best, n) => (n.position.x > best.position.x ? n : best));
  return { x: rightMost.position.x + NEW_NODE_OFFSET_X, y: rightMost.position.y };
};

// ---------------------------------------------------------------------------
// Edge factories (every edge the editor creates carries data.kind)
// ---------------------------------------------------------------------------

const withKind = (edge: Edge, kind: EdgeKind): Edge => ({ ...edge, data: { ...edge.data, kind } });

// Edge ids keep the historical formats so graphs saved before data.kind still line up
export const makeEdgeId = (kind: EdgeKind, source: string, target: string): string => {
  switch (kind) {
    case EDGE_KINDS.START:
      return `e-start-${target}`;
    case EDGE_KINDS.FILTER:
      return `e-filter-${source}-${target}`;
    case EDGE_KINDS.LOOP_EXEC:
      return `e-loop-exec-${source}-${target}`;
    case EDGE_KINDS.LOOP_RETURN:
      return `e-loop-return-${source}-${target}`;
    default:
      return `e-${source}-${target}`;
  }
};

const routeLabel = (targetId: string, condition?: string): string => {
  const text = condition || `to ${targetId}`;
  return text.length > ROUTE_LABEL_MAX_LENGTH ? `${text.substring(0, ROUTE_LABEL_MAX_LENGTH)}...` : text;
};

export const makeStartEdge = (triggerId: string, targetId: string): Edge => ({
  id: makeEdgeId(EDGE_KINDS.START, triggerId, targetId),
  source: triggerId,
  target: targetId,
  type: 'smoothstep',
  animated: true,
  deletable: false,
  style: { stroke: START_EDGE_COLOR, strokeWidth: 2 },
  data: { kind: EDGE_KINDS.START },
});

export const makeFlowEdge = (source: string, target: string, fromIterator = false): Edge => {
  const color = fromIterator ? ITERATOR_EDGE_COLOR : FLOW_EDGE_COLOR;
  return {
    id: makeEdgeId(EDGE_KINDS.FLOW, source, target),
    source,
    target,
    type: 'smoothstep',
    animated: true,
    style: { stroke: color, strokeWidth: 2 },
    label: fromIterator ? 'On Complete [All]' : undefined,
    labelStyle: fromIterator ? { fill: ITERATOR_EDGE_COLOR, fontSize: 9, fontWeight: 600 } : undefined,
    labelBgStyle: fromIterator ? { fill: 'hsl(var(--card))', stroke: ITERATOR_EDGE_COLOR, strokeWidth: 1 } : undefined,
    labelBgPadding: fromIterator ? ([6, 3] as [number, number]) : undefined,
    labelBgBorderRadius: fromIterator ? 4 : undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
    data: { kind: EDGE_KINDS.FLOW },
  };
};

export const makeRouteEdge = (routerId: string, targetId: string, condition?: string): Edge => ({
  id: makeEdgeId(EDGE_KINDS.ROUTE, routerId, targetId),
  source: routerId,
  target: targetId,
  type: 'smoothstep',
  label: routeLabel(targetId, condition),
  labelStyle: { fill: ROUTER_EDGE_COLOR, fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
  labelBgPadding: [6, 4] as [number, number],
  labelBgBorderRadius: 4,
  labelBgStyle: { fill: 'hsl(var(--background))', stroke: 'hsl(var(--border))', strokeWidth: 1 },
  style: { stroke: ROUTER_EDGE_COLOR, strokeWidth: 2 },
  data: { kind: EDGE_KINDS.ROUTE },
});

const makeFilterEdge = (dependency: string, targetId: string): Edge => ({
  id: makeEdgeId(EDGE_KINDS.FILTER, dependency, targetId),
  source: dependency,
  target: targetId,
  type: 'smoothstep',
  animated: false,
  style: { stroke: FILTER_EDGE_COLOR, strokeWidth: 1.2, strokeDasharray: '4,4', opacity: 0.35 },
  label: 'Filter',
  labelStyle: { fill: FILTER_EDGE_COLOR, fontSize: 8, opacity: 0.7 },
  data: { kind: EDGE_KINDS.FILTER },
});

const makeLoopEdges = (iteratorId: string, executeNode: string): Edge[] =>
  createIteratorLoopEdges(iteratorId, executeNode).map((e) => withKind(e, getEdgeKind(e)));

const createTriggerNode = (position: XYPosition): Node => ({
  id: TRIGGER_NODE_ID,
  type: NODE_TYPES.TRIGGER,
  position,
  deletable: false,
  data: {
    label: 'Workflow Trigger',
    description: 'Triggers the execution and hands off input to the entry agent.',
    type: 'trigger',
  },
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const findNode = (graph: Graph, id: string) => graph.nodes.find((n) => n.id === id);

const isStartEdge = (edge: Edge) => getEdgeKind(edge) === EDGE_KINDS.START;

// Entry node: the trigger edge's target, else the first agent (matches the serializer's fallback)
export const getStartNodeId = (graph: Graph): string => {
  const startEdge = graph.edges.find(isStartEdge);
  if (startEdge) return startEdge.target;
  return graph.nodes.find((n) => n.type === NODE_TYPES.AGENT)?.id ?? '';
};

const pickDefaultStart = (nodes: Node[]): Node | undefined =>
  nodes.find((n) => n.type === NODE_TYPES.AGENT) ?? nodes.find(isExecutableNode);

// Edges from a router are branches. Router edges created before data.kind existed classify as FLOW.
export const isRouteEdge = (edge: Edge, source: Node | undefined) => {
  if (source?.type !== NODE_TYPES.ROUTER) return false;
  const kind = getEdgeKind(edge);
  return kind === EDGE_KINDS.ROUTE || kind === EDGE_KINDS.FLOW;
};

// Whether `connection` may become an edge: no self-loops, nothing into the trigger, loop edges only via execute_node,
// router branches only to executable nodes, and no duplicate source->target edges
export const validateConnection = (connection: Connection | Edge, graph: Graph): boolean => {
  const { source, target } = connection;
  if (!source || !target || source === target) return false;
  const sourceNode = findNode(graph, source);
  const targetNode = findNode(graph, target);
  if (!sourceNode || !targetNode || targetNode.type === NODE_TYPES.TRIGGER) return false;
  // Loop-return edges are derived from the iterator's execute_node and cannot be drawn by hand
  if (connection.sourceHandle === LOOP_BACK_HANDLE || connection.targetHandle === LOOP_RETURN_HANDLE) return false;

  if (sourceNode.type === NODE_TYPES.TRIGGER) return isExecutableNode(targetNode);
  if (sourceNode.type === NODE_TYPES.ITERATOR && connection.sourceHandle === LOOP_OUT_HANDLE) {
    return isExecutableNode(targetNode);
  }
  if (sourceNode.type === NODE_TYPES.ROUTER) {
    return isExecutableNode(targetNode) && !hasOwn(getRoutingOptions(sourceNode), target);
  }
  // Without a router the runtime allows exactly one next node (flo_ai Arium.add_edge)
  return !graph.edges.some((e) => e.source === source && getEdgeKind(e) === EDGE_KINDS.FLOW);
};

// ---------------------------------------------------------------------------
// Building blocks (pure)
// ---------------------------------------------------------------------------

const patchNodeData = (graph: Graph, id: string, patch: Record<string, unknown>): Graph => {
  if (Object.keys(patch).length === 0) return graph;
  return {
    nodes: graph.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)),
    edges: graph.edges,
  };
};

// Rewrite every by-name reference one node holds to another node.
// `resolve` returns the new name, or null to drop the reference.
const remapReferences = (nodes: Node[], resolve: (id: string) => string | null): Node[] =>
  nodes.map((node) => {
    const data = node.data ?? {};
    const patch: Record<string, unknown> = {};

    const remapList = (list: unknown): unknown[] | undefined => {
      if (!Array.isArray(list)) return undefined;
      const next = list.flatMap((item) => {
        if (typeof item !== 'string') return [item];
        const resolved = resolve(item);
        return resolved === null ? [] : [resolved];
      });
      const changed = next.length !== list.length || next.some((item, i) => item !== list[i]);
      return changed ? next : undefined;
    };

    const inputFilter = remapList(data.input_filter);
    if (inputFilter) patch.input_filter = inputFilter.length > 0 ? inputFilter : undefined;

    const flowPattern = remapList(data.flow_pattern);
    if (flowPattern) patch.flow_pattern = flowPattern;

    if (node.type === NODE_TYPES.ROUTER) {
      // routing_options: target -> condition (keys are node names)
      const options = getRoutingOptions(node);
      let optionsChanged = false;
      const nextOptions: RoutingOptions = {};
      Object.entries(options).forEach(([target, condition]) => {
        const resolved = resolve(target);
        if (resolved !== target) optionsChanged = true;
        if (resolved !== null) nextOptions[resolved] = condition;
      });
      if (optionsChanged) patch.routing_options = nextOptions;

      // routes (field_match): match value -> target (values are node names)
      if (isPlainObject(data.routes)) {
        let routesChanged = false;
        const nextRoutes: Record<string, unknown> = {};
        Object.entries(data.routes).forEach(([match, target]) => {
          if (typeof target !== 'string') {
            nextRoutes[match] = target;
            return;
          }
          const resolved = resolve(target);
          if (resolved !== target) routesChanged = true;
          if (resolved !== null) nextRoutes[match] = resolved;
        });
        if (routesChanged) patch.routes = nextRoutes;
      }

      // default (field_match): fallback target
      if (typeof data.default === 'string' && data.default) {
        const resolved = resolve(data.default);
        if (resolved !== data.default) patch.default = resolved ?? undefined;
      }
    }

    if (typeof data.execute_node === 'string' && data.execute_node) {
      const resolved = resolve(data.execute_node);
      if (resolved !== data.execute_node) patch.execute_node = resolved ?? '';
    }

    if (typeof data.loopedBy === 'string' && data.loopedBy) {
      const resolved = resolve(data.loopedBy);
      if (resolved !== data.loopedBy) {
        patch.loopedBy = resolved ?? undefined;
        if (resolved === null) patch.isLoopTarget = false;
      }
    }

    return Object.keys(patch).length > 0 ? { ...node, data: { ...data, ...patch } } : node;
  });

// Point the trigger at `startId`, reusing the existing trigger node (creating one only when none exists)
const ensureStart = (graph: Graph, startId: string): Graph => {
  const target = findNode(graph, startId);
  if (!target || !isExecutableNode(target)) return graph;
  const trigger = graph.nodes.find((n) => n.type === NODE_TYPES.TRIGGER);
  const currentStart = graph.edges.filter(isStartEdge);
  if (trigger && currentStart.length === 1 && currentStart[0].target === startId) return graph;

  const triggerNode = trigger ?? createTriggerNode({ x: target.position.x - NEW_NODE_OFFSET_X, y: target.position.y });
  return {
    nodes: trigger ? graph.nodes : [triggerNode, ...graph.nodes],
    edges: [makeStartEdge(triggerNode.id, startId), ...graph.edges.filter((e) => !isStartEdge(e))],
  };
};

const removeStart = (graph: Graph): Graph => ({
  nodes: graph.nodes.filter((n) => n.type !== NODE_TYPES.TRIGGER),
  edges: graph.edges.filter((e) => !isStartEdge(e)),
});

// Point an iterator at a new execute_node: updates loop-target flags and the loop edge pair
const setExecuteNode = (graph: Graph, iteratorId: string, executeNode: string): Graph => {
  const iterator = findNode(graph, iteratorId);
  if (!iterator || iterator.type !== NODE_TYPES.ITERATOR) return graph;
  const previous = (iterator.data?.execute_node as string) || '';
  const hasLoopEdges = graph.edges.some(
    (e) =>
      (getEdgeKind(e) === EDGE_KINDS.LOOP_EXEC && e.source === iteratorId) ||
      (getEdgeKind(e) === EDGE_KINDS.LOOP_RETURN && e.target === iteratorId)
  );
  if (previous === executeNode && (hasLoopEdges || !executeNode)) return graph;

  const nodes = graph.nodes.map((node) => {
    if (node.id === iteratorId) return { ...node, data: { ...node.data, execute_node: executeNode } };
    if (executeNode && node.id === executeNode) {
      return { ...node, data: { ...node.data, isLoopTarget: true, loopedBy: iteratorId } };
    }
    if (previous && node.id === previous && node.data?.loopedBy === iteratorId) {
      // Another iterator may still execute this node
      const other = graph.nodes.find(
        (n) => n.type === NODE_TYPES.ITERATOR && n.id !== iteratorId && n.data?.execute_node === previous
      );
      return {
        ...node,
        data: { ...node.data, isLoopTarget: !!other, loopedBy: other?.id },
      };
    }
    return node;
  });

  const edges = graph.edges.filter(
    (e) =>
      !(
        (getEdgeKind(e) === EDGE_KINDS.LOOP_EXEC && e.source === iteratorId) ||
        (getEdgeKind(e) === EDGE_KINDS.LOOP_RETURN && e.target === iteratorId)
      )
  );
  const targetExists = !!executeNode && graph.nodes.some((n) => n.id === executeNode);
  return { nodes, edges: targetExists ? [...edges, ...makeLoopEdges(iteratorId, executeNode)] : edges };
};

// Rebuild the dashed input_filter edges into `nodeId` from its data
const syncFilterEdges = (graph: Graph, nodeId: string): Graph => {
  const node = findNode(graph, nodeId);
  if (!node) return graph;
  const deps = Array.isArray(node.data?.input_filter) ? (node.data.input_filter as unknown[]) : [];
  const nodeIds = new Set(graph.nodes.map((n) => n.id));
  const filterEdges = Array.from(new Set(deps))
    .filter((dep): dep is string => typeof dep === 'string' && dep !== 'input' && dep !== nodeId && nodeIds.has(dep))
    .map((dep) => makeFilterEdge(dep, nodeId));
  return {
    nodes: graph.nodes,
    edges: [
      ...graph.edges.filter((e) => !(getEdgeKind(e) === EDGE_KINDS.FILTER && e.target === nodeId)),
      ...filterEdges,
    ],
  };
};

// Reconcile router branch edges with each router's routing_options.
// Idempotent: a second call on its own output returns the same graph object.
export const syncRouterEdges = (graph: Graph): Graph => {
  const nodesById = new Map(graph.nodes.map((n) => [n.id, n]));
  const seen = new Set<string>();
  const branchKey = (routerId: string, targetId: string) => `${routerId}\u0000${targetId}`;
  let changed = false;
  const edges: Edge[] = [];

  graph.edges.forEach((edge) => {
    const router = nodesById.get(edge.source);
    if (!router || !isRouteEdge(edge, router)) {
      edges.push(edge);
      return;
    }
    const options = getRoutingOptions(router);
    const key = branchKey(edge.source, edge.target);
    // Drop branches that are no longer configured and duplicate edges for the same branch
    if (!hasOwn(options, edge.target) || seen.has(key)) {
      changed = true;
      return;
    }
    seen.add(key);
    const label = routeLabel(edge.target, options[edge.target]);
    if (edge.label !== label || edge.data?.kind !== EDGE_KINDS.ROUTE) {
      edges.push({ ...edge, label, data: { ...edge.data, kind: EDGE_KINDS.ROUTE } });
      changed = true;
    } else {
      edges.push(edge);
    }
  });

  graph.nodes.forEach((router) => {
    if (router.type !== NODE_TYPES.ROUTER) return;
    Object.entries(getRoutingOptions(router)).forEach(([targetId, condition]) => {
      const key = branchKey(router.id, targetId);
      if (seen.has(key) || !nodesById.has(targetId)) return;
      seen.add(key);
      edges.push(makeRouteEdge(router.id, targetId, condition));
      changed = true;
    });
  });

  return changed ? { nodes: graph.nodes, edges } : graph;
};

// Bring a graph from outside the reducer (parsed YAML, a template) to the invariants the editor relies on:
// unique node and edge ids, a non-deletable trigger, data.kind on every edge, router edges in sync.
export const normalizeGraph = (graph: Graph): Graph => {
  const nodeIds = new Set<string>();
  const nodes = graph.nodes
    .filter((n) => {
      if (nodeIds.has(n.id)) return false;
      nodeIds.add(n.id);
      return true;
    })
    .map((n) => (n.type === NODE_TYPES.TRIGGER && n.deletable !== false ? { ...n, deletable: false } : n));

  const edgeIds = new Set<string>();
  const edges = graph.edges
    .filter((e) => {
      if (edgeIds.has(e.id)) return false;
      edgeIds.add(e.id);
      return true;
    })
    .map((e) => {
      const kind = getEdgeKind(e);
      const protectedEdge = kind === EDGE_KINDS.START || kind === EDGE_KINDS.REFLECT;
      if (e.data?.kind === kind && (!protectedEdge || e.deletable === false)) return e;
      return { ...withKind(e, kind), ...(protectedEdge ? { deletable: false } : {}) };
    });

  return syncRouterEdges({ nodes, edges });
};

// After the YAML has been re-serialized, every node's config lives under its current id.
// data.yamlName (set on rename so the serializer can find the node's previous YAML entry) is re-pointed to the id.
export const settleYamlNames = (graph: Graph): Graph => {
  if (!graph.nodes.some((n) => n.data?.yamlName !== undefined && n.data.yamlName !== n.id)) return graph;
  return {
    nodes: graph.nodes.map((n) =>
      n.data?.yamlName !== undefined && n.data.yamlName !== n.id ? { ...n, data: { ...n.data, yamlName: n.id } } : n
    ),
    edges: graph.edges,
  };
};

// Whether a parsed graph came without positions (every node at the origin) and needs an initial layout
export const needsLayout = (graph: Graph): boolean =>
  graph.nodes.length > 1 && graph.nodes.every((n) => n.position.x === 0 && n.position.y === 0);

// Full dagre layout. Only for the explicit Auto-Layout action, templates and YAML parsed without positions:
// structural edits keep the user's manual positions.
export const layoutGraph = (graph: Graph): Graph => {
  // getLayoutedElements writes positions onto the nodes it is given, so hand it copies
  const laidOut = getLayoutedElements(
    graph.nodes.map((n) => ({ ...n })),
    graph.edges,
    'LR'
  );
  return { nodes: laidOut.nodes, edges: graph.edges };
};

// Keep the positions of nodes that already exist on the canvas when the graph is rebuilt from YAML
export const keepPositions = (graph: Graph, previous: Node[]): Graph => {
  const positions = new Map(previous.map((n) => [n.id, n.position]));
  return {
    nodes: graph.nodes.map((n) => {
      const position = positions.get(n.id);
      return position ? { ...n, position } : n;
    }),
    edges: graph.edges,
  };
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export type GraphAction =
  | { type: 'addNode'; node: Node; connectFrom?: { source: string; sourceHandle?: string | null } }
  | { type: 'updateNodeData'; id: string; patch: Record<string, unknown> }
  | { type: 'renameNode'; oldId: string; newId: string }
  | { type: 'deleteElements'; nodeIds?: string[]; edgeIds?: string[] }
  | { type: 'connect'; connection: Connection }
  | { type: 'setRouteCondition'; routerId: string; targetId: string; condition: string }
  | { type: 'setStart'; nodeId: string };

const connect = (graph: Graph, connection: Connection): Graph => {
  if (!validateConnection(connection, graph)) return graph;
  const { source, target } = connection;
  const sourceNode = findNode(graph, source)!;

  if (sourceNode.type === NODE_TYPES.TRIGGER) return ensureStart(graph, target);
  if (sourceNode.type === NODE_TYPES.ITERATOR && connection.sourceHandle === LOOP_OUT_HANDLE) {
    return setExecuteNode(graph, source, target);
  }
  if (sourceNode.type === NODE_TYPES.ROUTER) {
    // The branch edge itself is created by syncRouterEdges from routing_options
    return patchNodeData(graph, source, {
      routing_options: { ...getRoutingOptions(sourceNode), [target]: `Route to ${target}` },
    });
  }
  return {
    nodes: graph.nodes,
    edges: [...graph.edges, makeFlowEdge(source, target, sourceNode.type === NODE_TYPES.ITERATOR)],
  };
};

const addNode = (graph: Graph, node: Node, connectFrom?: { source: string; sourceHandle?: string | null }) => {
  if (graph.nodes.some((n) => n.id === node.id)) return graph;
  let next: Graph = { nodes: [...graph.nodes, node], edges: graph.edges };
  if (connectFrom) {
    next = connect(next, {
      source: connectFrom.source,
      sourceHandle: connectFrom.sourceHandle ?? null,
      target: node.id,
      targetHandle: null,
    });
  }
  // The first executable step becomes the workflow entry
  const isFirstStep = isExecutableNode(node) && !graph.nodes.some(isExecutableNode);
  if (isFirstStep && !next.edges.some(isStartEdge)) next = ensureStart(next, node.id);
  return next;
};

const updateNodeData = (graph: Graph, id: string, patch: Record<string, unknown>): Graph => {
  const node = findNode(graph, id);
  if (!node) return graph;
  const { execute_node: executeNode, ...rest } = patch;
  const changed = Object.entries(rest).some(([key, value]) => node.data?.[key] !== value);
  let next = changed ? patchNodeData(graph, id, rest) : graph;
  if (hasOwn(patch, 'execute_node')) {
    next =
      node.type === NODE_TYPES.ITERATOR
        ? setExecuteNode(next, id, (executeNode as string) || '')
        : patchNodeData(next, id, { execute_node: executeNode });
  }
  if (hasOwn(patch, 'input_filter') && node.data?.input_filter !== patch.input_filter) next = syncFilterEdges(next, id);
  return next;
};

const renameNode = (graph: Graph, oldId: string, newId: string): Graph => {
  const node = findNode(graph, oldId);
  if (!node || node.type === NODE_TYPES.TRIGGER || oldId === newId) return graph;
  if (validateNodeName(newId, graph.nodes, oldId)) return graph;

  const nodes = remapReferences(graph.nodes, (id) => (id === oldId ? newId : id)).map((n) =>
    n.id === oldId
      ? {
          ...n,
          id: newId,
          // yamlName: the name this node's config is stored under in the YAML, until the next serialize
          data: { ...n.data, label: newId, yamlName: n.data?.yamlName ?? oldId },
        }
      : n
  );
  const edges = graph.edges.map((edge) => {
    if (edge.source !== oldId && edge.target !== oldId) return edge;
    const kind = getEdgeKind(edge);
    const source = edge.source === oldId ? newId : edge.source;
    const target = edge.target === oldId ? newId : edge.target;
    // Reflection loop ids carry the router name and step index; they stay unique without rebuilding
    const id = kind === EDGE_KINDS.REFLECT ? edge.id : makeEdgeId(kind, source, target);
    return { ...edge, id, source, target, data: { ...edge.data, kind } };
  });
  return { nodes, edges };
};

const deleteNodes = (graph: Graph, ids: string[]): Graph => {
  // The trigger is owned by the editor and is never deleted directly
  const doomed = new Set(
    ids.filter((id) => {
      const node = findNode(graph, id);
      return !!node && node.type !== NODE_TYPES.TRIGGER;
    })
  );
  if (doomed.size === 0) return graph;
  const startId = graph.edges.find(isStartEdge)?.target;

  const nodes = remapReferences(
    graph.nodes.filter((n) => !doomed.has(n.id)),
    (id) => (doomed.has(id) ? null : id)
  );
  const next: Graph = { nodes, edges: graph.edges.filter((e) => !doomed.has(e.source) && !doomed.has(e.target)) };

  if (!startId || !doomed.has(startId)) return next;
  // The entry step was deleted: hand the trigger to the next step so canvas and YAML agree on workflow.start
  const fallback = pickDefaultStart(nodes);
  return fallback ? ensureStart(next, fallback.id) : removeStart(next);
};

const deleteEdge = (graph: Graph, edgeId: string): Graph => {
  const edge = graph.edges.find((e) => e.id === edgeId);
  if (!edge) return graph;
  const kind = getEdgeKind(edge);
  const without: Graph = { nodes: graph.nodes, edges: graph.edges.filter((e) => e.id !== edgeId) };
  const sourceNode = findNode(graph, edge.source);

  switch (kind) {
    case EDGE_KINDS.START:
    case EDGE_KINDS.REFLECT:
      // Derived from workflow.start / flow_pattern: change those settings instead
      return graph;
    case EDGE_KINDS.LOOP_EXEC:
      return setExecuteNode(graph, edge.source, '');
    case EDGE_KINDS.LOOP_RETURN:
      return setExecuteNode(graph, edge.target, '');
    case EDGE_KINDS.FILTER: {
      const target = findNode(graph, edge.target);
      const deps = Array.isArray(target?.data?.input_filter) ? (target.data.input_filter as unknown[]) : [];
      const kept = deps.filter((dep) => dep !== edge.source);
      return patchNodeData(without, edge.target, { input_filter: kept.length > 0 ? kept : undefined });
    }
    default:
      if (isRouteEdge(edge, sourceNode)) {
        const options = { ...getRoutingOptions(sourceNode!) };
        delete options[edge.target];
        return patchNodeData(without, edge.source, { routing_options: options });
      }
      return without;
  }
};

const reduceGraph = (graph: Graph, action: GraphAction): Graph => {
  switch (action.type) {
    case 'addNode':
      return addNode(graph, action.node, action.connectFrom);
    case 'updateNodeData':
      return updateNodeData(graph, action.id, action.patch);
    case 'renameNode':
      return renameNode(graph, action.oldId, action.newId);
    case 'deleteElements': {
      const afterNodes = deleteNodes(graph, action.nodeIds ?? []);
      return (action.edgeIds ?? []).reduce(deleteEdge, afterNodes);
    }
    case 'connect':
      return connect(graph, action.connection);
    case 'setRouteCondition': {
      const router = findNode(graph, action.routerId);
      if (router?.type !== NODE_TYPES.ROUTER) return graph;
      const options = getRoutingOptions(router);
      if (options[action.targetId] === action.condition) return graph;
      return patchNodeData(graph, action.routerId, {
        routing_options: { ...options, [action.targetId]: action.condition },
      });
    }
    case 'setStart':
      return ensureStart(graph, action.nodeId);
    default:
      return graph;
  }
};

// Apply one editor action. Returns the input graph object when the action changes nothing.
export const applyGraphAction = (graph: Graph, action: GraphAction): Graph => {
  const next = reduceGraph(graph, action);
  return next === graph ? graph : syncRouterEdges(next);
};
