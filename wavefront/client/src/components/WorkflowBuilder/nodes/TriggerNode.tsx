import { Handle, NodeProps } from '@xyflow/react';
import { Zap } from 'lucide-react';
import React from 'react';
import { Badge } from '@app/components/ui/badge';
import { useHandlePositions } from '../hooks/useWorkflowActions';
import { NodeCard } from './NodeCard';

export const TriggerNode = React.memo(({ data, selected }: NodeProps) => {
  const handles = useHandlePositions();
  return (
    <>
      <NodeCard
        title={(data.label as string) || 'Workflow Trigger'}
        icon={Zap}
        colorClass="bg-purple-500/10 text-purple-500"
        selected={selected}
        badge={
          <Badge variant="outline" className="border-purple-500/20 bg-purple-500/10 py-0 text-[10px] text-purple-500">
            Start Event
          </Badge>
        }
      >
        <div className="text-muted-foreground text-[11px] leading-relaxed">
          {(data.description as string) || 'Triggers the execution and hands off input to the entry agent.'}
        </div>
      </NodeCard>
      <Handle
        type="source"
        position={handles.source}
        className="border-background h-3.5 w-3.5 border-2 bg-purple-500"
      />
    </>
  );
});
