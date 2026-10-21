import { Trash2 } from 'lucide-react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { LlmModelOption, NodePropertiesProps } from './types';

interface RouterPropertiesProps extends NodePropertiesProps {
  rootfloConfigs: LlmModelOption[];
}

export const RouterProperties = ({ selectedNode, handleChange, nodes, rootfloConfigs }: RouterPropertiesProps) => {
  return (
    <>
      <div>
        <Label className="mb-1 block text-xs">Router Type</Label>
        <select
          className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
          value={(selectedNode.data.strategy as string) || (selectedNode.data.type as string) || 'smart'}
          onChange={(e) => handleChange('strategy', e.target.value)}
        >
          <option value="smart">Smart (LLM-based classification)</option>
          <option value="field_match">Field Match (Deterministic JSON match - No LLM)</option>
          <option value="reflection">Reflection Loop (Main ➔ Critic ➔ Main)</option>
          <option value="task_classifier">Task Classifier</option>
          <option value="conversation_analysis">Conversation Analysis</option>
          <option value="plan_execute">Plan & Execute</option>
        </select>
      </div>

      {/* FIELD MATCH ROUTER */}
      {(selectedNode.data.strategy === 'field_match' || selectedNode.data.type === 'field_match') && (
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

          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-[11px] text-emerald-600 dark:text-emerald-400">
            ⚡ <strong>Deterministic:</strong> Zero LLM latency or cost. Perfect for document classifiers and
            categorical routing.
          </div>
        </div>
      )}

      {/* REFLECTION ROUTER */}
      {(selectedNode.data.strategy === 'reflection' || selectedNode.data.type === 'reflection') && (
        <div className="bg-muted/20 border-border space-y-3 rounded-xl border p-2.5">
          <div>
            <Label className="mb-1 block text-xs font-semibold">Flow Pattern (Ordered Steps)</Label>
            <Input
              value={
                Array.isArray(selectedNode.data.flow_pattern)
                  ? selectedNode.data.flow_pattern.join(', ')
                  : (selectedNode.data.flow_pattern as string) || ''
              }
              onChange={(e) => {
                const arr = e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean);
                handleChange('flow_pattern', arr);
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
      {selectedNode.data.strategy !== 'field_match' && selectedNode.data.type !== 'field_match' && (
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
              <Input
                type="number"
                step="0.1"
                min="0"
                max="1"
                value={(selectedNode.data.temperature as string) ?? '0.3'}
                onChange={(e) => handleChange('temperature', e.target.value)}
                className="bg-background h-8 text-xs"
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs">Fallback Strategy</Label>
              <select
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                value={(selectedNode.data.fallback_strategy as string) || 'first'}
                onChange={(e) => handleChange('fallback_strategy', e.target.value)}
              >
                <option value="first">First</option>
                <option value="broadcast">Broadcast (All)</option>
                <option value="none">None (Fail)</option>
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
            className="text-primary text-[11px] font-medium hover:underline"
            onClick={() => {
              const current = (selectedNode.data.routing_options as Record<string, string>) || {};
              const availableNodes = nodes.filter((n) => n.id !== selectedNode.id && !current[n.id]);
              const targetKey =
                availableNodes.length > 0 ? availableNodes[0].id : `target_${Object.keys(current).length + 1}`;
              const defaultPrompt =
                selectedNode.data.strategy === 'field_match' ? 'exact_value_match' : 'Describe routing condition...';
              handleChange('routing_options', { ...current, [targetKey]: defaultPrompt });
            }}
          >
            + Add Branch
          </button>
        </div>

        <div className="bg-muted/20 border-border space-y-2.5 rounded-xl border p-2.5">
          {Object.entries((selectedNode.data.routing_options as Record<string, string>) || {}).map(([key, val]) => (
            <div key={key} className="bg-background border-border/60 space-y-1.5 rounded-lg border p-2">
              <div className="flex items-center justify-between gap-1.5">
                <span className="text-muted-foreground text-[10px] font-semibold">To:</span>
                <select
                  value={key}
                  onChange={(e) => {
                    const current = {
                      ...((selectedNode.data.routing_options as Record<string, string>) || {}),
                    };
                    const oldVal = current[key];
                    delete current[key];
                    current[e.target.value] = oldVal;
                    handleChange('routing_options', current);
                  }}
                  className="bg-card border-border focus:border-primary text-foreground h-6 flex-1 rounded border px-1.5 text-[11px] font-medium focus:outline-none"
                >
                  <option value={key}>{(nodes.find((n) => n.id === key)?.data?.label as string) || key}</option>
                  {nodes
                    .filter((n) => n.id !== selectedNode.id && n.id !== key)
                    .map((n) => (
                      <option key={n.id} value={n.id}>
                        {(n.data?.label as string) || n.id}
                      </option>
                    ))}
                </select>
                <button
                  className="text-muted-foreground hover:text-destructive hover:bg-muted rounded p-1"
                  onClick={() => {
                    const current = {
                      ...((selectedNode.data.routing_options as Record<string, string>) || {}),
                    };
                    delete current[key];
                    handleChange('routing_options', current);
                  }}
                  title="Remove branch"
                >
                  <Trash2 size={12} />
                </button>
              </div>
              <Input
                value={val}
                onChange={(e) => {
                  const current = { ...((selectedNode.data.routing_options as Record<string, string>) || {}) };
                  current[key] = e.target.value;
                  handleChange('routing_options', current);
                }}
                className="bg-card border-border h-7 text-[11px]"
                placeholder={
                  selectedNode.data.strategy === 'field_match'
                    ? 'Matched field value (e.g. invoice)...'
                    : 'Condition criteria...'
                }
              />
            </div>
          ))}
          {Object.keys((selectedNode.data.routing_options as Record<string, string>) || {}).length === 0 && (
            <p className="text-muted-foreground py-2 text-center text-[11px] italic">
              No branches connected yet. Click &quot;+ Add Branch&quot; above.
            </p>
          )}
        </div>
      </div>
    </>
  );
};
