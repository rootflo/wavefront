import React from 'react';
import { X, CheckCircle2, Star, Trash2 } from 'lucide-react';
import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Button } from '@app/components/ui/button';
import { useParams } from 'react-router';
import { useGetLLMConfigs, useGetWorkflows, useGetTools, useGetAgents } from '@app/hooks/data/fetch-hooks';
import MultiSelect from '@app/components/MultiSelect';
import { ParserBuilder } from './ParserBuilder';

interface PropertyPanelProps {
  selectedNode: Node | null;
  onClose: () => void;
  onUpdateNode: (id: string, data: Record<string, unknown>) => void;
  onRenameNode?: (oldId: string, newId: string) => void;
  nodes?: Node[];
  onSetStartAgent?: (agentId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
}

export const PropertyPanel = ({
  selectedNode,
  onClose,
  onUpdateNode,
  onRenameNode,
  nodes = [],
  onSetStartAgent,
  onDeleteNode,
}: PropertyPanelProps) => {
  const { app: appId } = useParams<{ app: string }>();
  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId || '');
  const { data: workflows = [] } = useGetWorkflows(appId || '');
  const { data: tools = [] } = useGetTools(appId || '');
  const { data: agents = [] } = useGetAgents(appId || '');

  const [nameInput, setNameInput] = React.useState((selectedNode?.data?.label as string) || selectedNode?.id || '');
  const [parserMode, setParserMode] = React.useState<'builder' | 'raw'>('builder');

  React.useEffect(() => {
    if (selectedNode) {
      setNameInput((selectedNode.data?.label as string) || selectedNode.id);
    }
  }, [selectedNode]);

  if (!selectedNode) return null;

  const handleChange = (key: string, value: unknown) => {
    onUpdateNode(selectedNode.id, { ...selectedNode.data, [key]: value });
  };

  const handleNameChange = (val: string) => {
    setNameInput(val);
    const sanitized = val.trim().replace(/\s+/g, '_');
    if (sanitized && sanitized !== selectedNode.id && !nodes.some((n) => n.id === sanitized)) {
      onRenameNode?.(selectedNode.id, sanitized);
    }
  };

  const handleNameBlur = () => {
    const sanitized = nameInput.trim().replace(/\s+/g, '_');
    if (!sanitized) {
      setNameInput((selectedNode.data?.label as string) || selectedNode.id);
    } else if (sanitized !== selectedNode.id) {
      onRenameNode?.(selectedNode.id, sanitized);
    }
  };

  const nodeTypeTitle = () => {
    switch (selectedNode.type) {
      case 'agentNode':
        return 'Agent Settings';
      case 'routerNode':
        return 'Router Settings';
      case 'functionNode':
        return 'Function Node Settings';
      case 'iteratorNode':
        return 'ForEach Iterator Settings';
      case 'subworkflowNode':
        return 'Sub-Workflow Settings';
      default:
        return 'Step Settings';
    }
  };

  return (
    <aside className="border-border bg-card z-10 flex h-full w-96 shrink-0 flex-col border-l shadow-[-2px_0_10px_rgba(0,0,0,0.05)]">
      <div className="border-border bg-muted/10 flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div>
          <h2 className="text-foreground text-xs font-semibold tracking-wider uppercase">{nodeTypeTitle()}</h2>
          <p className="text-muted-foreground max-w-[200px] truncate text-[10px]">{selectedNode.id}</p>
        </div>
        <button className="text-muted-foreground hover:text-foreground hover:bg-muted rounded p-1" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {/* ENTRY AGENT STATUS / BUTTON FOR AGENTS */}
        {selectedNode.type === 'agentNode' && (
          <div>
            {selectedNode.data.isStartNode ? (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={15} /> Workflow Entry Point
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="w-full gap-1.5 border-dashed text-xs hover:border-emerald-500 hover:text-emerald-500"
                onClick={() => onSetStartAgent?.(selectedNode.id)}
              >
                <Star size={13} /> Set as Workflow Entry Agent
              </Button>
            )}
          </div>
        )}

        <div>
          <Label className="mb-1 block text-xs">Identifier (Name)</Label>
          <Input
            value={nameInput}
            onChange={(e) => handleNameChange(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleNameBlur();
              }
            }}
            className="bg-background h-8 text-xs font-medium"
            placeholder="Unique name (e.g. content_creator)..."
          />
          <p className="text-muted-foreground mt-0.5 text-[10px]">Used as reference in workflow connections.</p>
        </div>

        {/* ========================================================================= */}
        {/* === AGENT PROPERTIES === */}
        {/* ========================================================================= */}
        {selectedNode.type === 'agentNode' && (
          <>
            <div>
              <Label className="text-primary mb-1 block text-xs font-semibold">Import Pre-built Agent (Optional)</Label>
              <Input
                list="agents-list"
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                value={(selectedNode.data.yaml_file as string) || ''}
                onChange={(e) => handleChange('yaml_file', e.target.value || undefined)}
                placeholder="Type or select a pre-built agent..."
              />
              <datalist id="agents-list">
                {agents.map((agent: { namespace?: string; name: string }) => (
                  <option key={`${agent.namespace}/${agent.name}`} value={`${agent.namespace}/${agent.name}`}>
                    {agent.name} ({agent.namespace})
                  </option>
                ))}
              </datalist>
              <p className="text-muted-foreground mt-0.5 text-[10px]">Overrides inline config if selected.</p>
            </div>

            <div className={selectedNode.data.yaml_file ? 'pointer-events-none space-y-4 opacity-50' : 'space-y-4'}>
              <div>
                <Label className="mb-1 block text-xs">Role</Label>
                <Input
                  value={(selectedNode.data.role as string) || ''}
                  onChange={(e) => handleChange('role', e.target.value)}
                  className="bg-background h-8 text-xs"
                  placeholder="e.g. Content Creator, Code Reviewer"
                />
                <p className="text-muted-foreground mt-0.5 text-[10px]">Title / functional role of this specialist.</p>
              </div>

              <div>
                <Label className="mb-1 block text-xs">Act As (Persona)</Label>
                <Input
                  value={(selectedNode.data.act_as as string) || ''}
                  onChange={(e) => handleChange('act_as', e.target.value)}
                  className="bg-background h-8 text-xs"
                  placeholder="e.g. assistant, senior_underwriter"
                />
              </div>

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
                  <Label className="mb-1 block text-xs">Model</Label>
                  {selectedNode.data.provider === 'rootflo' ? (
                    <select
                      className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                      value={(selectedNode.data.model as string) || ''}
                      onChange={(e) => handleChange('model', e.target.value)}
                    >
                      <option value="" disabled>
                        Select Model
                      </option>
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
                    value={(selectedNode.data.temperature as string) ?? '0.7'}
                    onChange={(e) => handleChange('temperature', e.target.value)}
                    className="bg-background h-8 text-xs"
                  />
                </div>
                <div className="flex-1">
                  <Label className="mb-1 block text-xs">Max Tokens</Label>
                  <Input
                    type="number"
                    placeholder="Optional"
                    value={(selectedNode.data.max_tokens as string) || ''}
                    onChange={(e) => handleChange('max_tokens', e.target.value)}
                    className="bg-background h-8 text-xs"
                  />
                </div>
              </div>

              <div>
                <Label className="mb-1 block text-xs">Job / System Prompt</Label>
                <textarea
                  className="bg-background border-border focus:border-primary text-foreground h-24 w-full resize-none rounded-md border px-3 py-2 text-xs leading-relaxed focus:outline-none"
                  value={(selectedNode.data.job as string) || ''}
                  onChange={(e) => handleChange('job', e.target.value)}
                  placeholder="Give this agent instructions on how to process incoming workflow requests..."
                />
                <p className="text-muted-foreground mt-0.5 text-[10px]">Core instructions executed by the agent.</p>
              </div>

              {/* Input Filter */}
              <div>
                <Label className="mb-1 block text-xs">Input Filter (Upstream Nodes)</Label>
                <MultiSelect
                  items={nodes.filter((n) => n.id !== selectedNode.id)}
                  selectedIds={Array.isArray(selectedNode.data.input_filter) ? selectedNode.data.input_filter : []}
                  onChange={(ids) => handleChange('input_filter', ids.length > 0 ? ids : undefined)}
                  getId={(n: Node) => n.id}
                  getLabel={(n: Node) => (n.data?.label as string) || n.id}
                  placeholder="Select upstream nodes..."
                  searchPlaceholder="Search nodes..."
                />
                <p className="text-muted-foreground mt-0.5 text-[10px]">
                  Nodes this agent reads from memory. Leave empty to read all.
                </p>
              </div>

              {/* Tools */}
              <div>
                <Label className="mb-1 block text-xs">Tools (Function Call Registry)</Label>
                <MultiSelect
                  items={tools as Array<{ name: string }>}
                  selectedIds={
                    Array.isArray(selectedNode.data.tools)
                      ? selectedNode.data.tools.map((t: unknown) =>
                          typeof t === 'string' ? t : ((t as { name?: string })?.name ?? '')
                        )
                      : []
                  }
                  onChange={(ids) => handleChange('tools', ids.length > 0 ? ids : undefined)}
                  getId={(t: { name: string }) => t.name}
                  getLabel={(t: { name: string }) => t.name}
                  placeholder="Select tools..."
                  searchPlaceholder="Search tools..."
                />
                <p className="text-muted-foreground mt-0.5 text-[10px]">
                  Names of tools available in registry for this agent.
                </p>
              </div>

              {/* Output Parser (JSON Schema) */}
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <Label className="block text-xs">Output Parser Schema (JSON / YAML)</Label>
                  <div className="bg-muted border-border flex overflow-hidden rounded border">
                    <button
                      className={`px-2 py-0.5 text-[10px] ${parserMode === 'builder' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/80'}`}
                      onClick={() => setParserMode('builder')}
                    >
                      Builder
                    </button>
                    <button
                      className={`px-2 py-0.5 text-[10px] ${parserMode === 'raw' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/80'}`}
                      onClick={() => setParserMode('raw')}
                    >
                      Raw JSON
                    </button>
                  </div>
                </div>
                {parserMode === 'builder' ? (
                  <ParserBuilder value={selectedNode.data.parser} onChange={(val) => handleChange('parser', val)} />
                ) : (
                  <textarea
                    className="bg-background border-border focus:border-primary text-foreground h-48 w-full resize-none rounded-md border px-3 py-2 font-mono text-xs focus:outline-none"
                    value={
                      typeof selectedNode.data.parser === 'object'
                        ? JSON.stringify(selectedNode.data.parser, null, 2)
                        : (selectedNode.data.parser as string) || ''
                    }
                    onChange={(e) => {
                      try {
                        const parsed = JSON.parse(e.target.value);
                        handleChange('parser', parsed);
                      } catch {
                        handleChange('parser', e.target.value);
                      }
                    }}
                    placeholder='{\n  "name": "MySchema",\n  "fields": []\n}'
                  />
                )}
                <p className="text-muted-foreground mt-1 text-[10px]">
                  Forces the agent to produce validated structured schema output.
                </p>
              </div>
            </div>
          </>
        )}

        {/* ========================================================================= */}
        {/* === ROUTER PROPERTIES === */}
        {/* ========================================================================= */}
        {selectedNode.type === 'routerNode' && (
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
                    <Label className="mb-1 block text-xs">Model</Label>
                    {selectedNode.data.provider === 'rootflo' ? (
                      <select
                        className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
                        value={(selectedNode.data.model as string) || ''}
                        onChange={(e) => handleChange('model', e.target.value)}
                      >
                        <option value="" disabled>
                          Select Model
                        </option>
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
                  <p className="text-muted-foreground mt-0.5 text-[10px]">
                    High-level intent guide for the LLM classifier.
                  </p>
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
                      selectedNode.data.strategy === 'field_match'
                        ? 'exact_value_match'
                        : 'Describe routing condition...';
                    handleChange('routing_options', { ...current, [targetKey]: defaultPrompt });
                  }}
                >
                  + Add Branch
                </button>
              </div>

              <div className="bg-muted/20 border-border space-y-2.5 rounded-xl border p-2.5">
                {Object.entries((selectedNode.data.routing_options as Record<string, string>) || {}).map(
                  ([key, val]) => (
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
                  )
                )}
                {Object.keys((selectedNode.data.routing_options as Record<string, string>) || {}).length === 0 && (
                  <p className="text-muted-foreground py-2 text-center text-[11px] italic">
                    No branches connected yet. Click &quot;+ Add Branch&quot; above.
                  </p>
                )}
              </div>
            </div>
          </>
        )}

        {/* ========================================================================= */}
        {/* === FUNCTION NODE PROPERTIES === */}
        {/* ========================================================================= */}
        {selectedNode.type === 'functionNode' && (
          <>
            <div>
              <Label className="mb-1 block text-xs">Function Registry Name</Label>
              <Input
                list="tools-list"
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
                value={(selectedNode.data.function_name as string) || ''}
                onChange={(e) => handleChange('function_name', e.target.value)}
                placeholder="Select or type a function name..."
              />
              <datalist id="tools-list">
                {tools.map((t: { name: string }) => (
                  <option key={t.name} value={t.name} />
                ))}
              </datalist>
              <p className="text-muted-foreground mt-0.5 text-[10px]">
                Exact callable name registered in the backend function registry.
              </p>
            </div>
            <div>
              <Label className="mb-1 block text-xs">Description</Label>
              <textarea
                className="bg-background border-border focus:border-primary text-foreground h-16 w-full resize-none rounded-md border px-3 py-2 text-xs focus:outline-none"
                value={(selectedNode.data.description as string) || ''}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="What this function node calculates or executes..."
              />
            </div>
            <div>
              <Label className="mb-1 block text-xs">Input Filter</Label>
              <MultiSelect
                items={nodes.filter((n) => n.id !== selectedNode.id)}
                selectedIds={Array.isArray(selectedNode.data.input_filter) ? selectedNode.data.input_filter : []}
                onChange={(ids) => handleChange('input_filter', ids.length > 0 ? ids : undefined)}
                getId={(n: Node) => n.id}
                getLabel={(n: Node) => (n.data?.label as string) || n.id}
                placeholder="Select upstream nodes..."
                searchPlaceholder="Search nodes..."
              />
              <p className="text-muted-foreground mt-0.5 text-[10px]">Nodes whose outputs this function consumes.</p>
            </div>
            <div>
              <Label className="mb-1 block text-xs">Prefilled Params (JSON)</Label>
              <textarea
                className="bg-background border-border focus:border-primary text-foreground h-24 w-full resize-none rounded-md border px-3 py-2 font-mono text-xs focus:outline-none"
                value={
                  typeof selectedNode.data.prefilled_params === 'object'
                    ? JSON.stringify(selectedNode.data.prefilled_params, null, 2)
                    : (selectedNode.data.prefilled_params as string) || ''
                }
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value);
                    handleChange('prefilled_params', parsed);
                  } catch {
                    handleChange('prefilled_params', e.target.value);
                  }
                }}
                placeholder='{\n  "message_processor_id": "123"\n}'
              />
            </div>
          </>
        )}

        {/* ========================================================================= */}
        {/* === ITERATOR NODE PROPERTIES === */}
        {/* ========================================================================= */}
        {selectedNode.type === 'iteratorNode' && (
          <>
            <div>
              <Label className="mb-1 block text-xs">Execute Target Node</Label>
              <select
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
                value={(selectedNode.data.execute_node as string) || ''}
                onChange={(e) => handleChange('execute_node', e.target.value)}
              >
                <option value="">Select target node...</option>
                {nodes
                  .filter((n) => n.id !== selectedNode.id)
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {(n.data?.label as string) || n.id} ({n.type?.replace('Node', '')})
                    </option>
                  ))}
              </select>
              <p className="text-muted-foreground mt-0.5 text-[10px]">
                Node executed on each item of the collection (e.g. a sub-workflow or agent).
              </p>
            </div>
            <div>
              <Label className="mb-1 block text-xs">Input Filter</Label>
              <MultiSelect
                items={nodes.filter((n) => n.id !== selectedNode.id)}
                selectedIds={Array.isArray(selectedNode.data.input_filter) ? selectedNode.data.input_filter : []}
                onChange={(ids) => handleChange('input_filter', ids.length > 0 ? ids : undefined)}
                getId={(n: Node) => n.id}
                getLabel={(n: Node) => (n.data?.label as string) || n.id}
                placeholder="Select upstream nodes..."
                searchPlaceholder="Search nodes..."
              />
              <p className="text-muted-foreground mt-0.5 text-[10px]">
                Source collection node to iterate over (default: all memory items).
              </p>
            </div>
            <div className="bg-muted/20 border-border mt-4 flex items-center gap-2 rounded-lg border p-2">
              <input
                type="checkbox"
                id="forward_all_results"
                checked={!!selectedNode.data.forward_all_results}
                onChange={(e) => handleChange('forward_all_results', e.target.checked)}
                className="border-border text-primary focus:ring-primary h-3.5 w-3.5 rounded"
              />
              <div>
                <Label htmlFor="forward_all_results" className="block text-xs font-semibold">
                  Forward All Results
                </Label>
                <p className="text-muted-foreground text-[10px]">
                  Forwards every per-item result into memory (otherwise only the final item is forwarded).
                </p>
              </div>
            </div>
          </>
        )}

        {/* ========================================================================= */}
        {/* === SUB-WORKFLOW (ARIUM) PROPERTIES === */}
        {/* ========================================================================= */}
        {selectedNode.type === 'subworkflowNode' && (
          <>
            <div>
              <Label className="mb-1 block text-xs">Workflow Reference / YAML File</Label>
              <Input
                list="workflows-list"
                className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
                value={(selectedNode.data.yaml_file as string) || (selectedNode.data.ref as string) || ''}
                onChange={(e) => {
                  handleChange('yaml_file', e.target.value);
                  handleChange('ref', e.target.value);
                }}
                placeholder="e.g. riskcovry-bridge/1a_doc_type_classifier"
              />
              <datalist id="workflows-list">
                {workflows.map((w: { namespace?: string; name: string }) => (
                  <option key={`${w.namespace}/${w.name}`} value={`${w.namespace}/${w.name}`}>
                    {w.name} ({w.namespace})
                  </option>
                ))}
              </datalist>
              <p className="text-muted-foreground mt-0.5 text-[10px]">
                Namespace/name or path to deployed sub-workflow.
              </p>
            </div>
            <div>
              <Label className="mb-1 block text-xs">Input Filter</Label>
              <MultiSelect
                items={nodes.filter((n) => n.id !== selectedNode.id)}
                selectedIds={Array.isArray(selectedNode.data.input_filter) ? selectedNode.data.input_filter : []}
                onChange={(ids) => handleChange('input_filter', ids.length > 0 ? ids : undefined)}
                getId={(n: Node) => n.id}
                getLabel={(n: Node) => (n.data?.label as string) || n.id}
                placeholder="Select upstream nodes..."
                searchPlaceholder="Search nodes..."
              />
              <p className="text-muted-foreground mt-0.5 text-[10px]">Which parent outputs this sub-workflow reads.</p>
            </div>
            <div className="bg-muted/20 border-border mt-4 flex items-center gap-2 rounded-lg border p-2">
              <input
                type="checkbox"
                id="inherit_variables"
                checked={selectedNode.data.inherit_variables !== false}
                onChange={(e) => handleChange('inherit_variables', e.target.checked)}
                className="border-border text-primary focus:ring-primary h-3.5 w-3.5 rounded"
              />
              <div>
                <Label htmlFor="inherit_variables" className="block text-xs font-semibold">
                  Inherit Variables
                </Label>
                <p className="text-muted-foreground text-[10px]">
                  Pass parent workflow variables into the sub-workflow during execution.
                </p>
              </div>
            </div>
          </>
        )}

        {/* DELETE ACTION BUTTON */}
        <div className="border-border border-t pt-4">
          <Button
            variant="outline"
            size="sm"
            className="text-destructive border-destructive/20 hover:bg-destructive/10 w-full gap-1.5 text-xs"
            onClick={() => onDeleteNode?.(selectedNode.id)}
          >
            <Trash2 size={13} /> Delete this {selectedNode.type?.replace('Node', '') || 'Step'}
          </Button>
        </div>
      </div>
    </aside>
  );
};
