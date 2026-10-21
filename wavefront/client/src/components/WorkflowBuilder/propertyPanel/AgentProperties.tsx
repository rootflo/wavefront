import React from 'react';
import { Node } from '@xyflow/react';
import { Badge } from '@app/components/ui/badge';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { AgentConfigMethod } from '@app/types/workflow-builder';
import { ParserBuilder } from '../ParserBuilder';
import { isExecutableNode } from '../graphUtils';
import { NumberInput } from './NumberInput';
import { LlmModelOption, NodePropertiesProps, ParserMode, ToolOption } from './types';

// A tool entry is a registry name or a config object (name plus prefilled_params / name_override / ...)
type ToolEntry = string | { name?: string; [key: string]: unknown };

const toolName = (tool: ToolEntry): string => (typeof tool === 'string' ? tool : (tool?.name ?? ''));

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const formatParser = (parser: unknown): string => {
  if (isPlainObject(parser)) return JSON.stringify(parser, null, 2);
  return typeof parser === 'string' ? parser : '';
};

const EXTERNAL_CONFIG_LABELS: Partial<Record<AgentConfigMethod, string>> = {
  reference: 'by reference',
  yaml_file: 'in a YAML file',
  yaml_config: 'in inline YAML config',
};

interface AgentPropertiesProps extends NodePropertiesProps {
  rootfloConfigs: LlmModelOption[];
  tools: ToolOption[];
  parserMode: ParserMode;
  onParserModeChange: (mode: ParserMode) => void;
}

export const AgentProperties = ({
  selectedNode,
  handleChange,
  handleChanges,
  nodes,
  rootfloConfigs,
  tools,
  parserMode,
  onParserModeChange,
}: AgentPropertiesProps) => {
  // Raw parser JSON is edited as text and only written to the node when it parses to an object,
  // so a half-typed schema never reaches the YAML as a string
  const [parserText, setParserText] = React.useState(() => formatParser(selectedNode.data.parser));
  const [parserError, setParserError] = React.useState<string | null>(null);

  const handleParserTextChange = (text: string) => {
    setParserText(text);
    if (!text.trim()) {
      setParserError(null);
      handleChange('parser', undefined);
      return;
    }
    try {
      const parsed = JSON.parse(text);
      if (!isPlainObject(parsed)) {
        setParserError('The parser must be a JSON object.');
        return;
      }
      setParserError(null);
      handleChange('parser', parsed);
    } catch {
      setParserError('Invalid JSON. The parser is not updated until this is valid.');
    }
  };

  const handleParserModeChange = (mode: ParserMode) => {
    // Entering raw mode shows the current parser; leaving it drops any unparsed text
    setParserText(formatParser(selectedNode.data.parser));
    setParserError(null);
    onParserModeChange(mode);
  };

  // Keep config objects (prefilled_params, name_override) for tools that stay selected
  const handleToolsChange = (ids: string[]) => {
    const current = (Array.isArray(selectedNode.data.tools) ? selectedNode.data.tools : []) as ToolEntry[];
    const next = ids.map((id) => current.find((t) => toolName(t) === id) ?? id);
    handleChange('tools', next.length > 0 ? next : undefined);
  };

  const configMethod = selectedNode.data.configMethod as AgentConfigMethod | undefined;
  const externalSource = configMethod ? EXTERNAL_CONFIG_LABELS[configMethod] : undefined;
  const readOnly = Boolean(externalSource);

  return (
    <>
      <div className="space-y-4">
        {externalSource && (
          <Badge variant="outline" className="text-[10px] font-normal">
            Job and model are configured {externalSource}; edit them there.
          </Badge>
        )}

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
            <Label className="mb-1 block text-xs">LLM Model</Label>
            <select
              className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs focus:outline-none"
              value={(selectedNode.data.model_id as string) || ''}
              disabled={readOnly}
              onChange={(e) => handleChanges({ provider: 'rootflo', model_id: e.target.value })}
            >
              <option value="">Select LLM Model</option>
              {rootfloConfigs.map((model: { id: string; display_name?: string; llm_model?: string }) => (
                <option key={model.id} value={model.id}>
                  {model.display_name || model.llm_model || model.id}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <Label className="mb-1 block text-xs">Temperature</Label>
            <NumberInput
              step="0.1"
              min={0}
              max={2}
              placeholder="0.7"
              value={selectedNode.data.temperature}
              onChange={(v) => handleChange('temperature', v)}
              className="bg-background h-8 text-xs"
            />
          </div>
          <div className="flex-1">
            <Label className="mb-1 block text-xs">Max Tokens</Label>
            <NumberInput
              min={1}
              step={1}
              placeholder="Optional"
              value={selectedNode.data.max_tokens}
              onChange={(v) => handleChange('max_tokens', v)}
              className="bg-background h-8 text-xs"
            />
          </div>
        </div>

        <div>
          <Label className="mb-1 block text-xs">Job / System Prompt</Label>
          <textarea
            className="bg-background border-border focus:border-primary text-foreground h-24 w-full resize-none rounded-md border px-3 py-2 text-xs leading-relaxed read-only:opacity-60 focus:outline-none"
            value={(selectedNode.data.job as string) || ''}
            readOnly={readOnly}
            onChange={(e) => handleChange('job', e.target.value)}
            placeholder="Give this agent instructions on how to process incoming workflow requests..."
          />
          <p className="text-muted-foreground mt-0.5 text-[10px]">Core instructions executed by the agent.</p>
        </div>

        {/* Input Filter */}
        <div>
          <Label className="mb-1 block text-xs">Input Filter (Upstream Nodes)</Label>
          <MultiSelect
            items={nodes.filter((n) => n.id !== selectedNode.id && isExecutableNode(n))}
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
              Array.isArray(selectedNode.data.tools) ? (selectedNode.data.tools as ToolEntry[]).map(toolName) : []
            }
            onChange={handleToolsChange}
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
                type="button"
                className={`px-2 py-0.5 text-[10px] ${parserMode === 'builder' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/80'}`}
                onClick={() => handleParserModeChange('builder')}
              >
                Builder
              </button>
              <button
                type="button"
                className={`px-2 py-0.5 text-[10px] ${parserMode === 'raw' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/80'}`}
                onClick={() => handleParserModeChange('raw')}
              >
                Raw JSON
              </button>
            </div>
          </div>
          {parserMode === 'builder' ? (
            <ParserBuilder value={selectedNode.data.parser} onChange={(val) => handleChange('parser', val)} />
          ) : (
            <>
              <textarea
                className={`bg-background focus:border-primary text-foreground h-48 w-full resize-none rounded-md border px-3 py-2 font-mono text-xs focus:outline-none ${parserError ? 'border-destructive' : 'border-border'}`}
                value={parserText}
                onChange={(e) => handleParserTextChange(e.target.value)}
                aria-invalid={!!parserError}
                placeholder='{\n  "name": "MySchema",\n  "fields": []\n}'
              />
              {parserError && <p className="text-destructive mt-0.5 text-[10px]">{parserError}</p>}
            </>
          )}
          <p className="text-muted-foreground mt-1 text-[10px]">
            Forces the agent to produce validated structured schema output.
          </p>
        </div>
      </div>
    </>
  );
};
