import { Handle, NodeProps } from '@xyflow/react';
import { GitBranch, CornerDownRight, RotateCcw } from 'lucide-react';
import React from 'react';
import { useParams } from 'react-router';
import { Badge } from '@app/components/ui/badge';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';
import { getRouterStrategy } from '../graphUtils';
import { useHandlePositions, useWorkflowActions } from '../hooks/useWorkflowActions';
import { NodeCard } from './NodeCard';

export const RouterNode = React.memo(({ id, data, selected }: NodeProps) => {
  const { startNodeId, deleteNode } = useWorkflowActions();
  const handles = useHandlePositions();
  const isStartNode = id === startNodeId;
  const routerType = getRouterStrategy(data);
  const branches = Object.entries((data.routing_options as Record<string, string>) || {});
  const isFieldMatch = routerType === 'field_match';
  const isReflection = routerType === 'reflection';

  const { app: appId } = useParams<{ app: string }>();
  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId || '');

  let resolvedModel = data.model as string;
  if (!resolvedModel && data.model_id) {
    const config = rootfloConfigs.find(
      (c: { id: string; display_name?: string; llm_model?: string }) => c.id === data.model_id
    );
    if (config) {
      resolvedModel = config.display_name || config.llm_model || config.id;
    }
  }

  const modelStr = resolvedModel || 'No LLM Selected';

  const typeLabels: Record<string, string> = {
    smart: 'Smart (LLM)',
    field_match: 'Field Match',
    reflection: 'Reflection Loop',
    task_classifier: 'Task Classifier',
    conversation_analysis: 'Conversation',
    plan_execute: 'Plan & Execute',
  };

  return (
    <>
      <Handle
        type="target"
        position={handles.target}
        className="border-background h-3.5 w-3.5 border-2 bg-orange-500"
      />
      <NodeCard
        title={(data.label as string) || 'Intent Router'}
        icon={isReflection ? RotateCcw : GitBranch}
        colorClass="bg-orange-500/10 text-orange-500"
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
              <Badge
                variant="outline"
                className="border-orange-500/20 bg-orange-500/10 py-0 text-[10px] text-orange-500"
              >
                {typeLabels[routerType] || routerType}
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
        {/* Router Specific Details */}
        {isFieldMatch && (
          <div className="rounded border border-orange-500/20 bg-orange-500/5 p-1.5 text-[11px]">
            <span className="text-muted-foreground">Match Field: </span>
            <code className="text-foreground bg-muted/40 rounded px-1 py-0.5 font-mono text-[10px] font-semibold">
              {(data.field as string) || 'Not set'}
            </code>
          </div>
        )}

        {isReflection && (
          <div className="rounded border border-orange-500/20 bg-orange-500/5 p-1.5 text-[11px]">
            <span className="text-muted-foreground mb-0.5 block">Flow Pattern:</span>
            <span className="text-foreground text-[10px] font-semibold">
              {Array.isArray(data.flow_pattern)
                ? data.flow_pattern.join(' ➔ ')
                : (data.flow_pattern as string) || 'None'}
            </span>
          </div>
        )}

        {/* Real branches preview */}
        <div className="flex flex-col gap-1.5">
          <div className="text-muted-foreground text-[10px] font-semibold tracking-wider uppercase">
            Decision Branches ({branches.length}):
          </div>
          {branches.length === 0 ? (
            <p className="text-muted-foreground bg-muted/20 border-border/50 rounded border p-2 text-center text-[11px] italic">
              No routes connected. Drag an edge to a target node.
            </p>
          ) : (
            branches.map(([target, condition]) => (
              <div
                key={target}
                className="bg-muted/30 border-border/40 flex items-center justify-between gap-1.5 rounded border px-2 py-1.5 text-[11px]"
              >
                <div className="flex items-center gap-1.5 overflow-hidden">
                  <CornerDownRight size={12} className="shrink-0 text-orange-500" />
                  <span className="text-foreground truncate font-semibold">{target}</span>
                </div>
                <span className="text-muted-foreground max-w-[120px] truncate text-[10px]" title={condition}>
                  {condition || (isFieldMatch ? `value == "${target}"` : 'When condition matches')}
                </span>
              </div>
            ))
          )}
        </div>

        {/* Footer: Deterministic vs LLM Model */}
        {isFieldMatch ? (
          <div className="border-border/60 text-muted-foreground flex items-center justify-between border-t pt-2 text-[10px]">
            <span className="font-medium text-emerald-600 dark:text-emerald-400">⚡ Deterministic (No LLM)</span>
            <span>Fast</span>
          </div>
        ) : (
          <div className="border-border/60 text-muted-foreground flex flex-col items-start gap-1 border-t pt-2 text-[10px]">
            <span className="truncate">Model: {modelStr}</span>
            <span>
              Fallback: <strong className="text-foreground">{(data.fallback_strategy as string) || 'first'}</strong>
            </span>
          </div>
        )}
      </NodeCard>
      <Handle
        type="source"
        position={handles.source}
        className="border-background h-3.5 w-3.5 border-2 bg-orange-500"
      />
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
