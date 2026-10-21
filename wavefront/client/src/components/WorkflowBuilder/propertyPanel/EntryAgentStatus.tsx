import { CheckCircle2, Star } from 'lucide-react';
import { Node } from '@xyflow/react';
import { Button } from '@app/components/ui/button';

interface EntryAgentStatusProps {
  selectedNode: Node;
  isStartNode: boolean;
  onSetStartAgent?: (agentId: string) => void;
}

export const EntryAgentStatus = ({ selectedNode, isStartNode, onSetStartAgent }: EntryAgentStatusProps) => {
  return (
    <div>
      {isStartNode ? (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 size={15} /> Workflow Entry Point
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-full gap-1.5 border-dashed text-xs hover:border-emerald-500 hover:text-emerald-500"
          onClick={() => onSetStartAgent?.(selectedNode.id)}
        >
          <Star size={13} /> Set as Workflow Entry Step
        </Button>
      )}
    </div>
  );
};
