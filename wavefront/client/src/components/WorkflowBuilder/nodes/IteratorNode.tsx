import { Handle, Position, NodeProps } from '@xyflow/react';
import { Repeat, RotateCcw } from 'lucide-react';
import React from 'react';
import { Badge } from '@app/components/ui/badge';
import { NodeCard } from './NodeCard';

export const IteratorNode = React.memo(({ data, selected }: NodeProps) => {
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];

  return (
    <>
      <Handle type="target" position={Position.Left} className="border-background h-3.5 w-3.5 border-2 bg-indigo-500" />
      <NodeCard
        title={(data.label as string) || 'Iterator'}
        icon={Repeat}
        colorClass="bg-indigo-500/10 text-indigo-500"
        selected={selected}
        badge={
          <div className="flex items-center gap-1">
            {Boolean(data.isStartNode) && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {Boolean(data.isEndNode) && (
              <Badge className="bg-purple-600 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🏁 End</Badge>
            )}
            {!data.isStartNode && !data.isEndNode && (
              <Badge
                variant="outline"
                className="flex items-center gap-1 border-indigo-500/30 bg-indigo-500/10 py-0 text-[10px] font-semibold text-indigo-500"
              >
                <Repeat size={10} className="animate-[spin_4s_linear_infinite]" />
                ForEach Loop
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
        onDelete={data.onDelete as (() => void) | undefined}
      >
        <div className="text-muted-foreground text-[11px] leading-relaxed">
          Loops over collection items and executes target step.
        </div>

        {/* Visual Loop Target Indicator */}
        <div className="flex items-center justify-between rounded-md border border-indigo-500/20 bg-indigo-500/10 px-2 py-1.5 text-[10px]">
          <span className="flex items-center gap-1 font-medium text-indigo-600 dark:text-indigo-400">
            <Repeat size={10} />
            Loop Target:
          </span>
          <span className="text-foreground max-w-[120px] truncate font-semibold">
            {(data.execute_node as string) || 'None'}
          </span>
        </div>

        <div className="border-border/60 text-muted-foreground flex flex-col gap-1 border-t pt-2 text-[10px]">
          <div className="flex justify-between">
            <span>Forward all results:</span>
            <span className="text-foreground font-semibold">
              {data.forward_all_results ? 'Yes (Full list)' : 'No (Last item)'}
            </span>
          </div>
          {inputFilters.length > 0 && (
            <div className="flex justify-between">
              <span>Input Filter:</span>
              <span className="text-foreground font-semibold">[{inputFilters.join(', ')}]</span>
            </div>
          )}
        </div>
      </NodeCard>

      {/* Primary Exit handle (when entire loop completes) */}
      <Handle
        type="source"
        position={Position.Right}
        className="border-background h-3.5 w-3.5 border-2 bg-indigo-500"
        title="On Loop Complete"
      />

      {/* Loop Cycle Handles */}
      {/* 1. Loop-Out: sends each item to the loop body */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="loop-out"
        style={{ left: '70%' }}
        className="border-background h-3.5 w-3.5 border-2 bg-indigo-600"
        title="Iterate Item (1..N)"
      />

      {/* 2. Loop-Return: receives the return cycle from the loop body */}
      <Handle
        type="target"
        position={Position.Bottom}
        id="loop-return"
        style={{ left: '30%' }}
        className="border-background h-3.5 w-3.5 border-2 bg-indigo-400"
        title="Loop Return (Next Item)"
      />

      {Boolean(data.isLoopTarget) && (
        <Handle
          type="source"
          position={Position.Bottom}
          id="loop-back"
          style={{ left: '50%' }}
          className="border-background h-3.5 w-3.5 border-2 bg-indigo-500"
          title="Return to Loop Iterator"
        />
      )}
    </>
  );
});
