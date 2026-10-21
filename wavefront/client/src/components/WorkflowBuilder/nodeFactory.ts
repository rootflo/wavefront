import { Node, XYPosition } from '@xyflow/react';
import { AddableNodeType, NODE_TYPES } from '@app/constants/workflow-builder';

// Build a new canvas node with default data for its type.
// `dataOverrides` lets callers replace defaults (e.g. agent job) or add extra fields (e.g. isStartNode).
export const createWorkflowNode = (
  type: AddableNodeType,
  id: string,
  position: XYPosition,
  dataOverrides: Record<string, unknown> = {}
): Node => ({
  id,
  type,
  position,
  data: {
    label: id,
    strategy: type === NODE_TYPES.ROUTER ? 'smart' : undefined,
    role: type === NODE_TYPES.AGENT ? 'General Assistant' : undefined,
    job: type === NODE_TYPES.AGENT ? 'Processes inputs and generates responses.' : undefined,
    provider: type === NODE_TYPES.AGENT || type === NODE_TYPES.ROUTER ? 'openai' : undefined,
    model: type === NODE_TYPES.AGENT || type === NODE_TYPES.ROUTER ? 'gpt-4o-mini' : undefined,
    temperature: type === NODE_TYPES.AGENT ? 0.7 : type === NODE_TYPES.ROUTER ? 0.3 : undefined,
    routing_options: type === NODE_TYPES.ROUTER ? {} : undefined,
    function_name: type === NODE_TYPES.FUNCTION ? 'passthrough' : undefined,
    execute_node: type === NODE_TYPES.ITERATOR ? '' : undefined,
    ...dataOverrides,
  },
});
