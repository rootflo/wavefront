import { NODE_TYPES } from '@app/constants/workflow-builder';
import { Node } from '@xyflow/react';
import { OutlineItem } from './OutlineItem';

interface OutlineSectionProps {
  nodes: Node[];
  selectedNodeId?: string;
  startAgentName?: string;
  onSelectNode?: (nodeId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
}

export const OutlineSection = ({
  nodes,
  selectedNodeId,
  startAgentName,
  onSelectNode,
  onDeleteNode,
}: OutlineSectionProps) => (
  <div>
    <div className="mb-2 flex items-center justify-between">
      <span className="text-muted-foreground text-[10px] font-bold tracking-wider uppercase">
        Outline ({nodes.length} nodes)
      </span>
    </div>

    <div className="space-y-1">
      {nodes
        .filter((n) => n.type !== NODE_TYPES.TRIGGER)
        .map((node) => (
          <OutlineItem
            key={node.id}
            node={node}
            isSelected={selectedNodeId === node.id}
            isStart={startAgentName === node.id}
            onSelectNode={onSelectNode}
            onDeleteNode={onDeleteNode}
          />
        ))}

      {nodes.length === 0 && (
        <p className="text-muted-foreground py-4 text-center text-[11px] italic">
          Canvas is empty. Click + to add components.
        </p>
      )}
    </div>
  </div>
);
