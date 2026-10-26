import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Plus, X } from 'lucide-react';
import React, { useId } from 'react';
import { ValuePair } from './values';

interface ValuesEditorProps {
  pairs: ValuePair[];
  onChange: (pairs: ValuePair[]) => void;
  /** Column names to suggest; any other name can still be typed. */
  columns: string[];
}

/** One row's values as column / value lines, so nobody has to hand-write JSON for a simple insert or update. */
const ValuesEditor: React.FC<ValuesEditorProps> = ({ pairs, onChange, columns }) => {
  const listId = useId();
  const set = (index: number, patch: Partial<ValuePair>) =>
    onChange(pairs.map((pair, i) => (i === index ? { ...pair, ...patch } : pair)));
  const unused = columns.filter((column) => !pairs.some((pair) => pair.column === column));

  return (
    <div className="flex flex-col gap-2">
      <datalist id={listId}>
        {unused.map((column) => (
          <option key={column} value={column} />
        ))}
      </datalist>
      {pairs.map((pair, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            list={listId}
            value={pair.column}
            onChange={(e) => set(index, { column: e.target.value })}
            placeholder="Column"
            aria-label="Column"
            className="h-9 w-44 shrink-0 font-mono text-xs"
          />
          <span className="frost-text-subtle text-xs">=</span>
          <Input
            value={pair.value}
            onChange={(e) => set(index, { value: e.target.value })}
            placeholder="Value"
            aria-label="Value"
            className="h-9 min-w-0 flex-1 font-mono text-xs"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Remove"
            onClick={() =>
              onChange(pairs.length === 1 ? [{ column: '', value: '' }] : pairs.filter((_, i) => i !== index))
            }
          >
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onChange([...pairs, { column: '', value: '' }])}
          className="text-brand inline-flex w-fit cursor-pointer items-center gap-1 text-xs font-medium"
        >
          <Plus className="size-3.5" />
          Add column
        </button>
        {unused.length > 0 && pairs.every((pair) => !pair.column.trim()) ? (
          <button
            type="button"
            onClick={() => onChange(columns.map((column) => ({ column, value: '' })))}
            className="frost-text-muted hover:text-frost-text cursor-pointer text-xs"
          >
            Fill in all {columns.length} columns
          </button>
        ) : null}
        <span className="frost-text-subtle text-xs">
          Numbers, true/false and null are stored as such; wrap in quotes to store them as text.
        </span>
      </div>
    </div>
  );
};

export default ValuesEditor;
