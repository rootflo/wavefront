import { Handle, Position, NodeProps } from '@xyflow/react';
import {
  Bot,
  GitBranch,
  Zap,
  Trash2,
  CornerDownRight,
  Cpu,
  Layers,
  Wrench,
  Filter,
  FileCode2,
  RotateCcw,
  Repeat,
} from 'lucide-react';
import React from 'react';
import { Badge } from '@app/components/ui/badge';

interface NodeCardProps {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  colorClass: string;
  selected?: boolean;
  badge?: React.ReactNode;
  onDelete?: () => void;
}

// Common card wrapper for all nodes
const NodeCard = ({ title, icon: Icon, children, colorClass, selected, badge, onDelete }: NodeCardProps) => {
  return (
    <div
      className={`bg-card w-72 rounded-xl border shadow-md transition-all ${
        selected ? 'border-primary ring-primary/20 shadow-lg ring-2' : 'border-border hover:border-border/80'
      }`}
    >
      <div className={`border-border flex items-center justify-between rounded-t-xl border-b p-3 ${colorClass}`}>
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="bg-background/60 text-foreground flex h-6 w-6 shrink-0 items-center justify-center rounded shadow-xs">
            <Icon size={14} />
          </div>
          <h4 className="text-foreground truncate text-xs font-semibold">{title}</h4>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {badge}
          {onDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              title="Delete node"
              className="text-muted-foreground hover:text-destructive hover:bg-background/50 rounded p-1 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="bg-card/50 flex flex-col gap-2 rounded-b-xl p-3 text-xs">{children}</div>
    </div>
  );
};

export const TriggerNode = React.memo(({ data, selected }: NodeProps) => {
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
        position={Position.Right}
        className="border-background h-3.5 w-3.5 border-2 bg-purple-500"
      />
    </>
  );
});

export const RouterNode = React.memo(({ data, selected }: NodeProps) => {
  const routerType = (data.strategy as string) || (data.type as string) || 'smart';
  const branches = Object.entries((data.routing_options as Record<string, string>) || {});
  const isFieldMatch = routerType === 'field_match';
  const isReflection = routerType === 'reflection';

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
      <Handle type="target" position={Position.Left} className="border-background h-3.5 w-3.5 border-2 bg-orange-500" />
      <NodeCard
        title={(data.label as string) || 'Intent Router'}
        icon={isReflection ? RotateCcw : GitBranch}
        colorClass="bg-orange-500/10 text-orange-500"
        selected={selected}
        badge={
          <div className="flex items-center gap-1">
            {data.isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {data.isEndNode && (
              <Badge className="bg-purple-600 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🏁 End</Badge>
            )}
            {!data.isStartNode && !data.isEndNode && (
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
        onDelete={data.onDelete}
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
          <div className="border-border/60 text-muted-foreground flex items-center justify-between border-t pt-2 text-[10px]">
            <span>Model: {(data.model as string) || 'gpt-4o-mini'}</span>
            <span>
              Fallback: <strong className="text-foreground">{(data.fallback_strategy as string) || 'first'}</strong>
            </span>
          </div>
        )}
      </NodeCard>
      <Handle
        type="source"
        position={Position.Right}
        className="border-background h-3.5 w-3.5 border-2 bg-orange-500"
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

export const AgentNode = React.memo(({ data, selected }: NodeProps) => {
  const tools = Array.isArray(data.tools) ? data.tools : [];
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];
  const hasParser = Boolean(data.parser);

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
            {data.isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {data.isEndNode && (
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
          {data.job && (
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
            <Cpu size={11} className="shrink-0" /> {(data.model as string) || 'gpt-4o-mini'} (
            {(data.provider as string) || 'openai'})
          </span>
          <span>Temp: {data.temperature ?? 0.7}</span>
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

export const FunctionNode = React.memo(({ data, selected }: NodeProps) => {
  const inputFilters = Array.isArray(data.input_filter) ? data.input_filter : [];

  return (
    <>
      <Handle type="target" position={Position.Left} className="border-background h-3.5 w-3.5 border-2 bg-blue-500" />
      <NodeCard
        title={(data.label as string) || 'Function'}
        icon={Cpu}
        colorClass="bg-blue-500/10 text-blue-500"
        selected={selected}
        badge={
          <div className="flex items-center gap-1">
            {data.isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {data.isEndNode && (
              <Badge className="bg-purple-600 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🏁 End</Badge>
            )}
            {!data.isStartNode && !data.isEndNode && (
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
        onDelete={data.onDelete as (() => void) | undefined}
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
          <span className="text-foreground max-w-[140px] truncate font-semibold">
            {(data.function_name as string) || 'passthrough'}
          </span>
        </div>
      </NodeCard>
      <Handle type="source" position={Position.Right} className="border-background h-3.5 w-3.5 border-2 bg-blue-500" />
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
            {data.isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {data.isEndNode && (
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

export const SubworkflowNode = React.memo(({ data, selected }: NodeProps) => {
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
            {data.isStartNode && (
              <Badge className="bg-emerald-500 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🚀 Start</Badge>
            )}
            {data.isEndNode && (
              <Badge className="bg-purple-600 px-1.5 py-0 text-[9px] font-medium text-white shadow-xs">🏁 End</Badge>
            )}
            {!data.isStartNode && !data.isEndNode && (
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
        onDelete={data.onDelete as (() => void) | undefined}
      >
        <div className="text-muted-foreground text-[11px] leading-relaxed">Nested sub-workflow execution block.</div>
        <div className="border-border/60 text-muted-foreground flex flex-col gap-1 border-t pt-2 text-[10px]">
          <div className="flex justify-between">
            <span>Reference / YAML:</span>
            <span
              className="text-foreground max-w-[130px] truncate font-semibold"
              title={(data.yaml_file as string) || (data.name as string)}
            >
              {(data.yaml_file as string) || (data.name as string) || 'inline'}
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
