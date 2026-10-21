import { Node } from '@xyflow/react';
import { Label } from '@app/components/ui/label';
import MultiSelect from '@app/components/MultiSelect';
import { NodePropertiesProps } from './types';

export const IteratorProperties = ({ selectedNode, handleChange, nodes }: NodePropertiesProps) => {
  return (
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
  );
};
