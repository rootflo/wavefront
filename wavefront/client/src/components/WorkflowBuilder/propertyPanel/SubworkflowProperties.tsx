import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { isExecutableNode } from '../graphUtils';
import { NodePropertiesProps, WorkflowOption } from './types';

interface SubworkflowPropertiesProps extends NodePropertiesProps {
  workflows: WorkflowOption[];
}

export const SubworkflowProperties = ({
  selectedNode,
  handleChange,
  handleChanges,
  nodes,
  workflows,
}: SubworkflowPropertiesProps) => {
  return (
    <>
      <div>
        <Label className="mb-1 block text-xs">Workflow Reference / YAML File</Label>
        <Input
          list="workflows-list"
          className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
          value={(selectedNode.data.yaml_file as string) || (selectedNode.data.ref as string) || ''}
          onChange={(e) => handleChanges({ yaml_file: e.target.value, ref: e.target.value })}
          placeholder="e.g. riskcovry-bridge/1a_doc_type_classifier"
        />
        <datalist id="workflows-list">
          {workflows.map((w: { namespace?: string; name: string }) => (
            <option key={`${w.namespace}/${w.name}`} value={`${w.namespace}/${w.name}`}>
              {w.name} ({w.namespace})
            </option>
          ))}
        </datalist>
        <p className="text-muted-foreground mt-0.5 text-[10px]">Namespace/name or path to deployed sub-workflow.</p>
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
  );
};
