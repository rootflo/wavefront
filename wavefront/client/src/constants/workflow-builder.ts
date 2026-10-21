/**
 * Node type constants for the visual workflow builder (React Flow node types)
 */

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
