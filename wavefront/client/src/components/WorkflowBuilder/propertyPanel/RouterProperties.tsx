import React from 'react';
import { Trash2 } from 'lucide-react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { getRouterStrategy, getRoutingOptions, isExecutableNode } from '../graphUtils';
import { NumberInput } from './NumberInput';
import { LlmModelOption, NodePropertiesProps } from './types';

interface RouterPropertiesProps extends NodePropertiesProps {
  rootfloConfigs: LlmModelOption[];
}

// Router types the panel can fully configure (flo_ai RouterConfigModel.type)
const EDITABLE_ROUTER_TYPES = [
  { value: 'smart', label: 'Smart (LLM-based classification)' },
  { value: 'field_match', label: 'Field Match (Deterministic JSON match - No LLM)' },
  { value: 'reflection', label: 'Reflection Loop (Main ➔ Critic ➔ Main)' },
];

// Valid runtime types whose required fields (task_categories / routing_logic / agents) only exist in YAML.
// Shown only for routers that already use them, and never offered as a switch target.
const YAML_ONLY_ROUTER_TYPES: Record<string, string> = {
  task_classifier: 'Task Classifier (edit in YAML)',
  conversation_analysis: 'Conversation Analysis (edit in YAML)',
  plan_execute: 'Plan & Execute (edit in YAML)',
};

const FALLBACK_STRATEGIES = [
  { value: 'first', label: 'First' },
  { value: 'random', label: 'Random' },
  { value: 'all', label: 'All' },
];

const parseFlowPattern = (text: string): string[] =>
  text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

const hasRoute = (options: Record<string, string>, target: string) =>
  Object.prototype.hasOwnProperty.call(options, target);

export const RouterProperties = ({
  selectedNode,
  handleChange,
  handleChanges,
  nodes,
  rootfloConfigs,
}: RouterPropertiesProps) => {
  const strategy = getRouterStrategy(selectedNode.data);
  const isFieldMatch = strategy === 'field_match';
  const isYamlOnly = Object.prototype.hasOwnProperty.call(YAML_ONLY_ROUTER_TYPES, strategy);
  const routingOptions = getRoutingOptions(selectedNode);
  const defaultTarget = (selectedNode.data.default as string) || '';
  const fallbackStrategy = (selectedNode.data.fallback_strategy as string) || 'first';

  // The flow pattern is edited as comma-separated text: a controlled value rebuilt from the array would swallow
  // the comma as soon as it is typed. The text is re-synced only when the stored pattern changes from elsewhere.
  const storedFlowPattern = Array.isArray(selectedNode.data.flow_pattern)
    ? (selectedNode.data.flow_pattern as string[]).join(', ')
    : '';
  const [flowPatternText, setFlowPatternText] = React.useState(storedFlowPattern);
  React.useEffect(() => {
    setFlowPatternText((text) => (parseFlowPattern(text).join(', ') === storedFlowPattern ? text : storedFlowPattern));
  }, [storedFlowPattern]);

  // Branch targets must be steps the runtime can execute, and each target can only be routed to once
  const branchCandidates = nodes.filter(
    (n) => n.id !== selectedNode.id && isExecutableNode(n) && !hasRoute(routingOptions, n.id)
  );

  return (
    <>
      <div>
        <Label className="mb-1 block text-xs">Router Type</Label>
        <select
          className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
          value={strategy}
          disabled={isYamlOnly}
          // strategy and type are both read by the serializer and the node card: keep them identical
          onChange={(e) => handleChanges({ strategy: e.target.value, type: e.target.value })}
        >
          {EDITABLE_ROUTER_TYPES.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
          {isYamlOnly && <option value={strategy}>{YAML_ONLY_ROUTER_TYPES[strategy]}</option>}
        </select>
        {isYamlOnly && (
          <p className="text-muted-foreground mt-0.5 text-[10px]">
            This router&apos;s configuration is edited in the YAML editor; the visual builder keeps its settings
            unchanged.
          </p>
        )}
      </div>

      {/* FIELD MATCH ROUTER */}
      {isFieldMatch && (
        <div className="bg-muted/20 border-border space-y-3 rounded-xl border p-2.5">
          <div>
            <Label className="mb-1 block text-xs font-semibold">JSON Field to Inspect</Label>
            <Input
              value={(selectedNode.data.field as string) || ''}
              onChange={(e) => handleChange('field', e.target.value)}
              className="bg-background h-8 font-mono text-xs"
              placeholder="e.g. doc_type or status"
            />
            <p className="text-muted-foreground mt-0.5 text-[10px]">
              Reads this field value from the predecessor node&apos;s output to determine route.
            </p>
          </div>

          <div>
            <Label className="mb-1 block text-xs font-semibold">Default target</Label>
            <select
              className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
              value={defaultTarget}
              onChange={(e) => handleChange('default', e.target.value || undefined)}
            >
              <option value="">None</option>
              {Object.keys(routingOptions).map((target) => (
                <option key={target} value={target}>
                  {(nodes.find((n) => n.id === target)?.data?.label as string) || target}
                </option>
              ))}
              {defaultTarget && !hasRoute(routingOptions, defaultTarget) && (
                <option value={defaultTarget} disabled>
                  {defaultTarget} (not a branch)
                </option>
              )}
            </select>
            <p className="text-muted-foreground mt-0.5 text-[10px]">
              Used when no branch value matches. Must be one of the branches below.
            </p>
          </div>

          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-[11px] text-emerald-600 dark:text-emerald-400">
            ⚡ <strong>Deterministic:</strong> Zero LLM latency or cost. Perfect for document classifiers and
            categorical routing.
          </div>
        </div>
      )}

      {/* REFLECTION ROUTER */}
      {strategy === 'reflection' && (
        <div className="bg-muted/20 border-border space-y-3 rounded-xl border p-2.5">
          <div>
            <Label className="mb-1 block text-xs font-semibold">Flow Pattern (Ordered Steps)</Label>
            <Input
              value={flowPatternText}
              onChange={(e) => {
                setFlowPatternText(e.target.value);
                handleChange('flow_pattern', parseFlowPattern(e.target.value));
              }}
              className="bg-background h-8 font-mono text-xs"
              placeholder="e.g. draft_agent, critic_agent, draft_agent, final_agent"
            />
            <p className="text-muted-foreground mt-0.5 text-[10px]">
              Sequence of nodes in the reflection loop (e.g. A ➔ B ➔ A ➔ C).
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="allow_early_exit"
              checked={!!selectedNode.data.allow_early_exit}
              onChange={(e) => handleChange('allow_early_exit', e.target.checked)}
              className="border-border text-primary focus:ring-primary h-3.5 w-3.5 rounded"
            />
            <Label htmlFor="allow_early_exit" className="text-xs">
              Allow early exit if critique passes
            </Label>
          </div>
        </div>
      )}

      {/* LLM ROUTER SETTINGS (Hidden for field_match) */}
      {!isFieldMatch && (
        <>
          <div className="flex gap-2">
            <div className="flex-1">
              <Label className="mb-1 block text-xs">Provider</Label>
              <select
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                value={(selectedNode.data.provider as string) || 'openai'}
                onChange={(e) => handleChange('provider', e.target.value)}
              >
                <option value="openai">OpenAI</option>
                <option value="gemini">Google (Gemini)</option>
                <option value="anthropic">Anthropic</option>
                <option value="rootflo">RootFlo Models</option>
                <option value="vertexai">Vertex AI</option>
                <option value="azure_openai">Azure OpenAI</option>
              </select>
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs">LLM Model</Label>
              {selectedNode.data.provider === 'rootflo' ? (
                <select
                  className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                  value={(selectedNode.data.model_id as string) || ''}
                  onChange={(e) => handleChange('model_id', e.target.value)}
                >
                  <option value="">Select LLM Model</option>
                  {rootfloConfigs.map((model: { id: string; display_name?: string; llm_model?: string }) => (
                    <option key={model.id} value={model.id}>
                      {model.display_name || model.llm_model || model.id}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  value={(selectedNode.data.model as string) || ''}
                  onChange={(e) => handleChange('model', e.target.value)}
                  className="bg-background h-8 text-xs"
                  placeholder="e.g. gpt-4o-mini"
                />
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <Label className="mb-1 block text-xs">Temperature</Label>
              <NumberInput
                step="0.1"
                min={0}
                max={2}
                placeholder="0.3"
                value={selectedNode.data.temperature}
                onChange={(v) => handleChange('temperature', v)}
                className="bg-background h-8 text-xs"
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs">Fallback Strategy</Label>
              <select
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                value={fallbackStrategy}
                onChange={(e) => handleChange('fallback_strategy', e.target.value)}
              >
                {FALLBACK_STRATEGIES.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
                {/* A value from YAML the runtime does not implement: shown so it can be replaced */}
                {!FALLBACK_STRATEGIES.some((f) => f.value === fallbackStrategy) && (
                  <option value={fallbackStrategy} disabled>
                    {fallbackStrategy} (unsupported)
                  </option>
                )}
              </select>
            </div>
          </div>

          <div>
            <Label className="mb-1 block text-xs">Context Description</Label>
            <textarea
              className="bg-background border-border focus:border-primary text-foreground h-20 w-full resize-none rounded-md border px-3 py-2 text-xs leading-relaxed focus:outline-none"
              value={(selectedNode.data.context_description as string) || ''}
              onChange={(e) => handleChange('context_description', e.target.value)}
              placeholder="Describe how the router should evaluate context..."
            />
            <p className="text-muted-foreground mt-0.5 text-[10px]">High-level intent guide for the LLM classifier.</p>
          </div>
        </>
      )}

      {/* ROUTING OPTIONS / BRANCHES FOR ALL ROUTER TYPES */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <Label className="block text-xs font-semibold">Routing Branches (Targets)</Label>
          <button
            type="button"
            className="text-primary text-[11px] font-medium hover:underline disabled:cursor-not-allowed disabled:no-underline disabled:opacity-50"
            disabled={branchCandidates.length === 0}
            title={branchCandidates.length === 0 ? 'Every step on the canvas is already a branch' : undefined}
            onClick={() => {
              const target = branchCandidates[0];
              if (!target) return;
              handleChange('routing_options', {
                ...routingOptions,
                [target.id]: isFieldMatch ? '' : 'Describe routing condition...',
              });
            }}
          >
            + Add Branch
          </button>
        </div>

        <div className="bg-muted/20 border-border space-y-2.5 rounded-xl border p-2.5">
          {Object.entries(routingOptions).map(([key, val]) => (
            <div key={key} className="bg-background border-border/60 space-y-1.5 rounded-lg border p-2">
              <div className="flex items-center justify-between gap-1.5">
                <span className="text-muted-foreground text-[10px] font-semibold">To:</span>
                <select
                  value={key}
                  onChange={(e) => {
                    // Re-key the branch in place so the branch order is kept
                    const next: Record<string, string> = {};
                    Object.entries(routingOptions).forEach(([target, condition]) => {
                      next[target === key ? e.target.value : target] = condition;
                    });
                    if (isFieldMatch && defaultTarget === key) {
                      handleChanges({ routing_options: next, default: e.target.value });
                    } else {
                      handleChange('routing_options', next);
                    }
                  }}
                  className="bg-card border-border focus:border-primary text-foreground h-6 flex-1 rounded border px-1.5 text-[11px] font-medium focus:outline-none"
                >
                  <option value={key}>{(nodes.find((n) => n.id === key)?.data?.label as string) || key}</option>
                  {branchCandidates.map((n) => (
                    <option key={n.id} value={n.id}>
                      {(n.data?.label as string) || n.id}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive hover:bg-muted rounded p-1"
                  onClick={() => {
                    const current = { ...routingOptions };
                    delete current[key];
                    if (isFieldMatch && defaultTarget === key) {
                      handleChanges({ routing_options: current, default: undefined });
                    } else {
                      handleChange('routing_options', current);
                    }
                  }}
                  title="Remove branch"
                >
                  <Trash2 size={12} />
                </button>
              </div>
              <Input
                value={val}
                onChange={(e) => handleChange('routing_options', { ...routingOptions, [key]: e.target.value })}
                className="bg-card border-border h-7 text-[11px]"
                placeholder={
                  isFieldMatch ? 'Matched value(s), separate with | (e.g. invoice | receipt)' : 'Condition criteria...'
                }
              />
            </div>
          ))}
          {Object.keys(routingOptions).length === 0 && (
            <p className="text-muted-foreground py-2 text-center text-[11px] italic">
              No branches connected yet. Click &quot;+ Add Branch&quot; above.
            </p>
          )}
        </div>
      </div>
    </>
  );
};
