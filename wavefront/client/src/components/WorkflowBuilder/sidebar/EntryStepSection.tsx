import { NODE_TYPES } from '@app/constants/workflow-builder';
import { Node } from '@xyflow/react';

interface EntryStepSectionProps {
  nodes: Node[];
  startAgentName?: string;
  onSetStartAgent?: (agentName: string) => void;
}

export const EntryStepSection = ({ nodes, startAgentName, onSetStartAgent }: EntryStepSectionProps) => (
  <div className="bg-muted/20 border-border rounded-xl border p-2.5">
    <span className="text-muted-foreground mb-1.5 block text-[10px] font-bold tracking-wider uppercase">
      ⚡ Workflow Entry Agent
    </span>
    <select
      className="bg-background border-border text-foreground focus:border-primary w-full rounded-md border px-2 py-1 text-xs focus:outline-none"
      value={startAgentName || ''}
      onChange={(e) => onSetStartAgent?.(e.target.value)}
    >
      {nodes.filter((n) => n.type !== NODE_TYPES.TRIGGER).length === 0 && <option value="">No steps on canvas</option>}
      {nodes
        .filter((n) => n.type !== NODE_TYPES.TRIGGER)
        .map((node) => (
          <option key={node.id} value={node.id}>
            🚀 {(node.data?.label as string) || node.id} {(node.data?.role as string) ? `(${node.data.role})` : ''}
          </option>
        ))}
    </select>
  </div>
);
