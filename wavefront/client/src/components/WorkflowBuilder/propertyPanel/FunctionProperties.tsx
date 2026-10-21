import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { NodePropertiesProps, ToolOption } from './types';

interface FunctionPropertiesProps extends NodePropertiesProps {
  tools: ToolOption[];
}

export const FunctionProperties = ({ selectedNode, handleChange, nodes, tools }: FunctionPropertiesProps) => {
  return (
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
  );
};
