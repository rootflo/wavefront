import { Handle, Position, NodeProps } from '@xyflow/react';
import { Bot, Cpu, Filter, FileCode2, RotateCcw, Wrench } from 'lucide-react';
import React from 'react';
import { useParams } from 'react-router';
import { Badge } from '@app/components/ui/badge';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';
import { NodeCard } from './NodeCard';

export const AgentNode = React.memo(({ data, selected }: NodeProps) => {
  const tools = Array.isArray(data.tools) ? data.tools : [];
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];
  const hasParser = Boolean(data.parser);

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
  const providerStr = (data.provider as string) || ((data.model_id as string) ? 'rootflo' : 'openai');

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        className="border-background h-3.5 w-3.5 border-2 bg-emerald-500"
      />
      <NodeCard
        title={(data.label as string) || 'Agent'}
        icon={Bot}
        colorClass="bg-emerald-500/10 text-emerald-500"
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
                className="border-emerald-500/20 bg-emerald-500/10 py-0 text-[10px] text-emerald-500"
              >
                Agent
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
        {/* Role & System Prompt Snippet */}
        <div>
          <span className="text-foreground block text-[11px] font-semibold">
            {(data.role as string) || 'General Assistant'}
          </span>
          {(data.job as string) && (
            <p className="text-muted-foreground bg-muted/20 border-border/40 mt-1 line-clamp-2 rounded border p-1.5 text-[10px] italic">
              &ldquo;{data.job as string}&rdquo;
            </p>
          )}
        </div>

        {/* Feature Tags (Tools, Input Filter, Parser) */}
        {(tools.length > 0 || inputFilters.length > 0 || hasParser) && (
          <div className="flex flex-wrap gap-1 pt-1">
            {tools.length > 0 && (
              <Badge variant="secondary" className="flex items-center gap-1 px-1.5 py-0 text-[9px] font-normal">
                <Wrench size={9} /> {tools.length} tool{tools.length > 1 ? 's' : ''}
              </Badge>
            )}
            {inputFilters.length > 0 && (
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border-blue-500/20 bg-blue-500/10 px-1.5 py-0 text-[9px] font-normal text-blue-600 dark:text-blue-400"
              >
                <Filter size={9} /> filter: [{inputFilters.join(', ')}]
              </Badge>
            )}
            {hasParser && (
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border-purple-500/20 bg-purple-500/10 px-1.5 py-0 text-[9px] font-normal text-purple-600 dark:text-purple-400"
              >
                <FileCode2 size={9} /> Schema
              </Badge>
            )}
          </div>
        )}

        {/* Parser Payload Preview */}
        {hasParser &&
          typeof data.parser === 'object' &&
          Array.isArray((data.parser as Record<string, unknown>).fields) && (
            <div className="border-border/60 text-muted-foreground flex flex-col gap-1 border-t pt-2 text-[10px]">
              <span className="font-semibold text-purple-600 dark:text-purple-400">Schema Output:</span>
              <div className="flex flex-wrap gap-1">
                {(data.parser as { fields: { name: string }[] }).fields.slice(0, 4).map((f) => (
                  <span
                    key={f.name}
                    className="text-foreground rounded border border-purple-500/20 bg-purple-500/10 px-1 py-0.5 text-[9px]"
                  >
                    {f.name}
                  </span>
                ))}
                {(data.parser as { fields: { name: string }[] }).fields.length > 4 && (
                  <span className="text-foreground rounded border border-purple-500/20 bg-purple-500/10 px-1 py-0.5 text-[9px]">
                    + {(data.parser as { fields: { name: string }[] }).fields.length - 4} more
                  </span>
                )}
              </div>
            </div>
          )}

        {/* Model Footer */}
        <div className="border-border/60 text-muted-foreground flex items-center justify-between border-t pt-2 text-[10px]">
          <span className="flex max-w-[170px] items-center gap-1 truncate">
            <Cpu size={11} className="shrink-0" /> {modelStr} ({providerStr})
          </span>
          <span>Temp: {(data.temperature as number) ?? 0.7}</span>
        </div>
      </NodeCard>
      <Handle
        type="source"
        position={Position.Right}
        className="border-background h-3.5 w-3.5 border-2 bg-emerald-500"
      />
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
