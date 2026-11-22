import { Handle, NodeProps } from '@xyflow/react';
import { Cpu, Filter, RotateCcw } from 'lucide-react';
import React from 'react';
import { Badge } from '@app/components/ui/badge';
import { useHandlePositions, useWorkflowActions } from '../hooks/useWorkflowActions';
import { NodeCard } from './NodeCard';

export const FunctionNode = React.memo(({ id, data, selected }: NodeProps) => {
  const { startNodeId, deleteNode } = useWorkflowActions();
  const handles = useHandlePositions();
  const isStartNode = id === startNodeId;
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];
  // The runtime rejects a function node without a registered function name
  const functionName = (data.function_name as string) || '';

  return (
    <>
      <Handle type="target" position={handles.target} className="border-background h-3.5 w-3.5 border-2 bg-blue-500" />
      <NodeCard
        title={(data.label as string) || 'Function'}
        icon={Cpu}
        colorClass="bg-blue-500/10 text-blue-500"
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
              <Badge variant="outline" className="border-blue-500/20 bg-blue-500/10 py-0 text-[10px] text-blue-500">
                Function
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
        <div className="text-muted-foreground text-[11px] leading-relaxed">
          {(data.description as string) || 'Executes deterministic logic.'}
        </div>

        {inputFilters.length > 0 && (
          <div className="flex items-center gap-1 rounded border border-blue-500/20 bg-blue-500/10 p-1 text-[10px] text-blue-600 dark:text-blue-400">
            <Filter size={10} />
            <span>Reads: [{inputFilters.join(', ')}]</span>
          </div>
        )}

        <div className="border-border/60 text-muted-foreground flex items-center justify-between border-t pt-2 text-[10px]">
          <span className="text-muted-foreground">Registry Name:</span>
          {functionName ? (
            <span className="text-foreground max-w-[140px] truncate font-semibold">{functionName}</span>
          ) : (
            <span className="text-destructive font-semibold">Not set</span>
          )}
        </div>
      </NodeCard>
      <Handle type="source" position={handles.source} className="border-background h-3.5 w-3.5 border-2 bg-blue-500" />
      {Boolean(data.isLoopTarget) && (
        <Handle
          type="source"
          position={handles.side}
          id="loop-back"
          className="border-background h-3.5 w-3.5 border-2 bg-indigo-500"
          title="Return to Loop Iterator"
        />
      )}
    </>
  );
});
