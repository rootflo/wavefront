import { Handle, Position, NodeProps } from '@xyflow/react';
import { Layers, RotateCcw } from 'lucide-react';
import React from 'react';
import { Badge } from '@app/components/ui/badge';
import { useWorkflowActions } from '../hooks/useWorkflowActions';
import { NodeCard } from './NodeCard';

export const SubworkflowNode = React.memo(({ id, data, selected }: NodeProps) => {
  const { startNodeId, deleteNode } = useWorkflowActions();
  const isStartNode = id === startNodeId;
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];

  return (
    <>
      <Handle type="target" position={Position.Left} className="border-background h-3.5 w-3.5 border-2 bg-teal-500" />
      <NodeCard
        title={(data.label as string) || 'Sub-Workflow'}
        icon={Layers}
        colorClass="bg-teal-500/10 text-teal-500"
        selected={selected}
        badge={
          <div className="flex items-center gap-1">
            {isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {Boolean(data.isEndNode) && (
              <Badge className="bg-purple-600 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🏁 End</Badge>
            )}
            {!isStartNode && !data.isEndNode && (
              <Badge variant="outline" className="border-teal-500/20 bg-teal-500/10 py-0 text-[10px] text-teal-500">
                Arium
              </Badge>
            )}
            {Boolean(data.isLoopTarget) && (
              <Badge
                variant="outline"
                className="flex items-center gap-1 border-indigo-500/40 bg-indigo-500/10 py-0 text-[10px] font-medium text-indigo-500 dark:text-indigo-400"
              >
                <RotateCcw size={9} /> Loop Target
              </Badge>
            )}
          </div>
        }
        onDelete={() => deleteNode(id)}
      >
        <div className="text-muted-foreground text-[11px] leading-relaxed">Nested sub-workflow execution block.</div>
        <div className="border-border/60 text-muted-foreground flex flex-col gap-1 border-t pt-2 text-[10px]">
          <div className="flex justify-between">
            <span>Reference / YAML:</span>
            <span
              className="text-foreground max-w-[130px] truncate font-semibold"
              title={(data.ref as string) ?? (data.yaml_file as string) ?? (data.name as string)}
            >
              {(data.ref as string) ?? (data.yaml_file as string) ?? (data.name as string) ?? 'inline'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Inherit Variables:</span>
            <span className="text-foreground font-semibold">{data.inherit_variables !== false ? 'Yes' : 'No'}</span>
          </div>
          {inputFilters.length > 0 && (
            <div className="flex justify-between">
              <span>Input Filter:</span>
              <span className="text-foreground font-semibold">[{inputFilters.join(', ')}]</span>
            </div>
          )}
        </div>
      </NodeCard>
      <Handle type="source" position={Position.Right} className="border-background h-3.5 w-3.5 border-2 bg-teal-500" />
      {Boolean(data.isLoopTarget) && (
        <Handle
          type="source"
          position={Position.Bottom}
          id="loop-back"
          className="border-background h-3.5 w-3.5 border-2 bg-indigo-500"
          title="Return to Loop Iterator"
        />
      )}
    </>
  );
});
