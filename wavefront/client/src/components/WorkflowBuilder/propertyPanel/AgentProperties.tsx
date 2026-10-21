import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { ParserBuilder } from '../ParserBuilder';
import { LlmModelOption, NodePropertiesProps, ParserMode, ToolOption } from './types';

interface AgentPropertiesProps extends NodePropertiesProps {
  rootfloConfigs: LlmModelOption[];
  tools: ToolOption[];
  parserMode: ParserMode;
  onParserModeChange: (mode: ParserMode) => void;
}

export const AgentProperties = ({
  selectedNode,
  handleChange,
  nodes,
  rootfloConfigs,
  tools,
  parserMode,
  onParserModeChange,
}: AgentPropertiesProps) => {
  return (
    <>
      <div className="space-y-4">
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
              onChange={(e) => {
                handleChange('provider', 'rootflo');
                handleChange('model_id', e.target.value);
              }}
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
                onClick={() => onParserModeChange('builder')}
              >
                Builder
              </button>
              <button
                className={`px-2 py-0.5 text-[10px] ${parserMode === 'raw' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/80'}`}
                onClick={() => onParserModeChange('raw')}
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
  );
};
