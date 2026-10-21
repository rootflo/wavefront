/**
 * Node type constants for the visual workflow builder (React Flow node types)
 */

// Same rule as the server's validate_agent_workflow_name (agents_module/utils/validation_utils.py)
export const AGENT_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/;

export const AGENT_ID_PATTERN_MESSAGE = 'Letters, numbers, - and _ only; must start with a letter or number';

export const TEMPERATURE_RANGE = { min: 0, max: 2, step: 0.1 } as const;

export const NODE_TYPES = {
  TRIGGER: 'triggerNode',
  AGENT: 'agentNode',
  ROUTER: 'routerNode',
  FUNCTION: 'functionNode',
  ITERATOR: 'iteratorNode',
  SUBWORKFLOW: 'subworkflowNode',
} as const;

export type NodeType = (typeof NODE_TYPES)[keyof typeof NODE_TYPES];

// Node types a user can add to the canvas (the trigger is created automatically)
export type AddableNodeType = Exclude<NodeType, typeof NODE_TYPES.TRIGGER>;

export interface NodeTypeDefinition {
  type: NodeType;
  // Prefix used when generating unique node ids (e.g. agent_1)
  prefix: string;
}

export const NODE_TYPE_DEFINITIONS: NodeTypeDefinition[] = [
  { type: NODE_TYPES.AGENT, prefix: 'agent' },
  { type: NODE_TYPES.ROUTER, prefix: 'router' },
  { type: NODE_TYPES.FUNCTION, prefix: 'function' },
  { type: NODE_TYPES.ITERATOR, prefix: 'iterator' },
  { type: NODE_TYPES.SUBWORKFLOW, prefix: 'subworkflow' },
];

export const getNodeTypeDefinition = (type?: string): NodeTypeDefinition | undefined =>
  NODE_TYPE_DEFINITIONS.find((definition) => definition.type === type);

// Semantic kind of a canvas edge. Stored on `edge.data.kind` so meaning never depends on edge ids or colours.
export const EDGE_KINDS = {
  START: 'start', // trigger -> entry node
  FLOW: 'flow', // plain workflow edge (from -> to)
  ROUTE: 'route', // router -> branch target
  FILTER: 'filter', // input_filter visual dependency (not a workflow edge)
  LOOP_EXEC: 'loop-exec', // iterator -> executed node
  LOOP_RETURN: 'loop-return', // executed node -> iterator
  REFLECT: 'reflect', // reflection router loop-back
} as const;

export type EdgeKind = (typeof EDGE_KINDS)[keyof typeof EDGE_KINDS];

// Edge kinds that are visual-only and must never be serialized as workflow edges
export const NON_FLOW_EDGE_KINDS: EdgeKind[] = [
  EDGE_KINDS.FILTER,
  EDGE_KINDS.LOOP_EXEC,
  EDGE_KINDS.LOOP_RETURN,
  EDGE_KINDS.REFLECT,
];

const LEGACY_EDGE_ID_PREFIXES: [string, EdgeKind][] = [
  ['e-start-', EDGE_KINDS.START],
  ['e-filter-', EDGE_KINDS.FILTER],
  ['e-loop-exec-', EDGE_KINDS.LOOP_EXEC],
  ['e-loop-return-', EDGE_KINDS.LOOP_RETURN],
  ['e-reflect-', EDGE_KINDS.REFLECT],
];

// Read an edge's kind; falls back to the legacy id-prefix convention for edges created before `data.kind` existed
export const getEdgeKind = (edge: { id: string; data?: Record<string, unknown> }): EdgeKind => {
  const kind = edge.data?.kind as EdgeKind | undefined;
  if (kind) return kind;
  const legacy = LEGACY_EDGE_ID_PREFIXES.find(([prefix]) => edge.id.startsWith(prefix));
  return legacy ? legacy[1] : EDGE_KINDS.FLOW;
};
