import React from 'react';
import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { isExecutableNode } from '../graphUtils';
import { NodePropertiesProps, ToolOption } from './types';

interface FunctionPropertiesProps extends NodePropertiesProps {
  tools: ToolOption[];
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const formatParams = (params: unknown): string => {
  if (isPlainObject(params)) return JSON.stringify(params, null, 2);
  return typeof params === 'string' ? params : '';
};

export const FunctionProperties = ({ selectedNode, handleChange, nodes, tools }: FunctionPropertiesProps) => {
  // prefilled_params must be a mapping at runtime: keep the text locally and only store it once it parses to an object
  const [paramsText, setParamsText] = React.useState(() => formatParams(selectedNode.data.prefilled_params));
  const [paramsError, setParamsError] = React.useState<string | null>(null);

  const handleParamsChange = (text: string) => {
    setParamsText(text);
    if (!text.trim()) {
      setParamsError(null);
      handleChange('prefilled_params', undefined);
      return;
    }
    try {
      const parsed = JSON.parse(text);
      if (!isPlainObject(parsed)) {
        setParamsError('Prefilled params must be a JSON object, e.g. {"key": "value"}.');
        return;
      }
      setParamsError(null);
      handleChange('prefilled_params', parsed);
    } catch {
      setParamsError('Invalid JSON. The params are not updated until this is valid.');
    }
  };

  const functionName = (selectedNode.data.function_name as string) || '';

  return (
    <>
      <div>
        <Label className="mb-1 block text-xs">Function Registry Name</Label>
        <Input
          list="tools-list"
          className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
          value={functionName}
          onChange={(e) => handleChange('function_name', e.target.value)}
          placeholder="Select or type a function name..."
          aria-invalid={!functionName}
        />
        <datalist id="tools-list">
          {tools.map((t: { name: string }) => (
            <option key={t.name} value={t.name} />
          ))}
        </datalist>
        <p className={`mt-0.5 text-[10px] ${functionName ? 'text-muted-foreground' : 'text-destructive'}`}>
          {functionName
            ? 'Exact callable name registered in the backend function registry.'
            : 'Required: the workflow cannot run until a registered function is set.'}
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
          items={nodes.filter((n) => n.id !== selectedNode.id && isExecutableNode(n))}
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
          className={`bg-background focus:border-primary text-foreground h-24 w-full resize-none rounded-md border px-3 py-2 font-mono text-xs focus:outline-none ${paramsError ? 'border-destructive' : 'border-border'}`}
          value={paramsText}
          onChange={(e) => handleParamsChange(e.target.value)}
          aria-invalid={!!paramsError}
          placeholder='{\n  "message_processor_id": "123"\n}'
        />
        {paramsError && <p className="text-destructive mt-0.5 text-[10px]">{paramsError}</p>}
      </div>
    </>
  );
};
