import dagre from 'dagre';
import type { Edge, Node, XYPosition } from '@xyflow/react';
import { EDGE_KINDS, NODE_TYPES, getEdgeKind } from '@app/constants/workflow-builder';
import type { LayoutDirection } from './layoutDirection';

// Cards are w-72
const NODE_WIDTH = 288;

const ESTIMATED_HEIGHTS: Record<string, number> = {
  [NODE_TYPES.TRIGGER]: 110,
  [NODE_TYPES.AGENT]: 230,
  [NODE_TYPES.FUNCTION]: 170,
  [NODE_TYPES.ITERATOR]: 210,
  [NODE_TYPES.SUBWORKFLOW]: 170,
};
const ROUTER_BASE_HEIGHT = 150;
const ROUTER_ROW_HEIGHT = 28;
const DEFAULT_HEIGHT = 200;

// Clearance kept between neighbours; the rank gap also hosts edge labels
const SPACING: Record<LayoutDirection, { nodesep: number; ranksep: number }> = {
  LR: { nodesep: 70, ranksep: 130 },
  TB: { nodesep: 90, ranksep: 110 },
};
const MARGIN = 50;

const LABEL_CHAR_WIDTH = 6.5;
const LABEL_HEIGHT = 24;

// The edge kinds that decide the ranks. Data-dependency (filter), reflection and loop-return edges point backwards
// or skip ranks and would wreck the pipeline's reading order.
const isStructuralEdge = (edge: Edge): boolean => {
  const kind = getEdgeKind(edge);
  return kind !== EDGE_KINDS.FILTER && kind !== EDGE_KINDS.REFLECT && kind !== EDGE_KINDS.LOOP_RETURN;
};

// Edges that leave and enter through the default handles can follow the computed route; loop edges use side handles
const isRoutableEdge = (edge: Edge): boolean => {
  const kind = getEdgeKind(edge);
  const routableKind = kind === EDGE_KINDS.FLOW || kind === EDGE_KINDS.ROUTE || kind === EDGE_KINDS.START;
  return routableKind && !edge.sourceHandle && !edge.targetHandle;
};

export interface EdgeRoute {
  // Waypoints from source to target, in canvas coordinates
  points: XYPosition[];
  labelPosition?: XYPosition;
  // Node positions the route was computed for; once either node moves the route is stale
  sourcePosition: XYPosition;
  targetPosition: XYPosition;
}

export const ROUTED_EDGE_TYPE = 'routed';

export const getNodeSize = (node: Node): { width: number; height: number } => {
  const width = node.measured?.width ?? node.width ?? NODE_WIDTH;
  const measuredHeight = node.measured?.height ?? node.height;
  if (measuredHeight) return { width, height: measuredHeight };

  let height = ESTIMATED_HEIGHTS[node.type || ''] ?? DEFAULT_HEIGHT;
  if (node.type === NODE_TYPES.ROUTER) {
    const options = node.data?.routing_options;
    const routes = options && typeof options === 'object' ? Object.keys(options).length : 0;
    height = ROUTER_BASE_HEIGHT + routes * ROUTER_ROW_HEIGHT;
  }
  return { width, height };
};

const labelSize = (edge: Edge): { width: number; height: number } => {
  const text = typeof edge.label === 'string' ? edge.label : '';
  return { width: Math.ceil(text.length * LABEL_CHAR_WIDTH) + 20, height: LABEL_HEIGHT };
};

export const getLayoutedElements = (nodes: Node[], edges: Edge[], direction: LayoutDirection = 'LR') => {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  const spacing = SPACING[direction];
  graph.setGraph({
    rankdir: direction,
    nodesep: spacing.nodesep,
    ranksep: spacing.ranksep,
    edgesep: 30,
    marginx: MARGIN,
    marginy: MARGIN,
    acyclicer: 'greedy',
    ranker: 'network-simplex',
  });

  const sizes = new Map<string, { width: number; height: number }>();
  nodes.forEach((node) => {
    const size = getNodeSize(node);
    sizes.set(node.id, size);
    graph.setNode(node.id, size);
  });

  const laidOutEdges = edges.filter(
    (edge) => isStructuralEdge(edge) && sizes.has(edge.source) && sizes.has(edge.target) && edge.source !== edge.target
  );
  laidOutEdges.forEach((edge) => {
    const label = edge.label ? labelSize(edge) : { width: 0, height: 0 };
    graph.setEdge(edge.source, edge.target, { ...label, labelpos: 'c' }, edge.id);
  });

  dagre.layout(graph);

  const positions = new Map<string, XYPosition>();
  const layoutedNodes = nodes.map((node) => {
    const placed = graph.node(node.id);
    const size = sizes.get(node.id)!;
    if (!placed) return node;
    const position = { x: Math.round(placed.x - size.width / 2), y: Math.round(placed.y - size.height / 2) };
    positions.set(node.id, position);
    return { ...node, position };
  });

  const routable = new Set(laidOutEdges.filter(isRoutableEdge).map((edge) => edge.id));
  const layoutedEdges = edges.map((edge): Edge => {
    if (!routable.has(edge.id)) return stripRoute(edge);
    const placed = graph.edge({ v: edge.source, w: edge.target, name: edge.id });
    const sourcePosition = positions.get(edge.source);
    const targetPosition = positions.get(edge.target);
    if (!placed?.points || !sourcePosition || !targetPosition) return stripRoute(edge);
    const route: EdgeRoute = {
      points: placed.points.map((p: XYPosition) => ({ x: p.x, y: p.y })),
      labelPosition: edge.label && placed.x !== undefined ? { x: placed.x, y: placed.y } : undefined,
      sourcePosition,
      targetPosition,
    };
    return { ...edge, type: ROUTED_EDGE_TYPE, data: { ...edge.data, route } };
  });

  return { nodes: layoutedNodes, edges: layoutedEdges };
};

// An edge that is not part of the computed layout falls back to the stock smoothstep curve
const stripRoute = (edge: Edge): Edge => {
  if (edge.type !== ROUTED_EDGE_TYPE && !edge.data?.route) return edge;
  const data = { ...edge.data };
  delete data.route;
  return { ...edge, type: 'smoothstep', data };
};
