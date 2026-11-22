import { Node } from '@xyflow/react';

export type ParserMode = 'builder' | 'raw';

export type LlmModelOption = { id: string; display_name?: string; llm_model?: string };

export type ToolOption = { name: string };

export type WorkflowOption = { namespace?: string; name: string };

export interface NodePropertiesProps {
  selectedNode: Node;
  // Both merge into the node's current data; use handleChanges when several fields change together
  handleChange: (key: string, value: unknown) => void;
  handleChanges: (patch: Record<string, unknown>) => void;
  nodes: Node[];
}
