import { Node, XYPosition } from '@xyflow/react';
import { AddableNodeType, NODE_TYPES } from '@app/constants/workflow-builder';

// Build a new canvas node with default data for its type.
// `dataOverrides` lets callers replace defaults (e.g. agent job) or add extra fields (e.g. yaml_file).
// Agents and routers start on RootFlo with no model chosen (model_id ''), so the serializer writes no model block and
// reports the missing model instead of saving one RootFlo cannot resolve. Temperature is left unset so the provider
// default applies unless the user picks one.
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
    provider: type === NODE_TYPES.AGENT || type === NODE_TYPES.ROUTER ? 'rootflo' : undefined,
    model_id: type === NODE_TYPES.AGENT || type === NODE_TYPES.ROUTER ? '' : undefined,
    routing_options: type === NODE_TYPES.ROUTER ? {} : undefined,
    // No default function: the user must pick one from the registry
    function_name: type === NODE_TYPES.FUNCTION ? '' : undefined,
    execute_node: type === NODE_TYPES.ITERATOR ? '' : undefined,
    ...dataOverrides,
  },
});
