import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Plus, X } from 'lucide-react';
import React, { useId, useState } from 'react';
import { buildFilter, FILTER_OPERATORS, FilterCondition, FilterJoin, FilterOperator } from './odata-filter';

interface FilterBuilderProps {
  /** Column names to suggest; any other name can still be typed. */
  columns: string[];
  /** The filter text. Editing conditions rewrites it; in text mode it is edited directly. */
  value: string;
  onChange: (filter: string) => void;
  /** The text mode's placeholder, e.g. "loan_id eq '1234'". */
  placeholder?: string;
}

const emptyCondition = (column = ''): FilterCondition => ({ column, operator: 'eq', value: '' });

/**
 * Conditions picked from a column, an operator and a value, written out as an OData filter, so nobody has to
 * remember the syntax. "Edit as text" switches to the raw string for anything the rows can't express.
 */
const FilterBuilder: React.FC<FilterBuilderProps> = ({ columns, value, onChange, placeholder }) => {
  const listId = useId();
  const [conditions, setConditions] = useState<FilterCondition[]>([emptyCondition()]);
  const [join, setJoin] = useState<FilterJoin>('$and');
  // Starts in text mode when there is already a filter the rows did not write.
  const [textMode, setTextMode] = useState(Boolean(value));

  const update = (nextConditions: FilterCondition[], nextJoin = join) => {
    setConditions(nextConditions);
    setJoin(nextJoin);
    onChange(buildFilter(nextConditions, nextJoin));
  };

  const setCondition = (index: number, patch: Partial<FilterCondition>) =>
    update(conditions.map((condition, i) => (i === index ? { ...condition, ...patch } : condition)));

  if (textMode) {
    return (
      <div className="flex flex-col gap-2">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="font-mono"
        />
        <button
          type="button"
          onClick={() => {
            setTextMode(false);
            onChange(buildFilter(conditions, join));
          }}
          className="text-brand w-fit cursor-pointer text-xs font-medium"
        >
          Use the filter builder
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <datalist id={listId}>
        {columns.map((column) => (
          <option key={column} value={column} />
        ))}
      </datalist>
      {conditions.map((condition, index) => (
        // One line per condition, however narrow: column and value share what's left after the fixed parts.
        <div key={index} className="flex items-center gap-1.5">
          {index === 0 ? (
            <span className="frost-text-muted w-12 shrink-0 text-xs">Where</span>
          ) : index === 1 ? (
            <Select value={join} onValueChange={(next) => update(conditions, next as FilterJoin)}>
              <SelectTrigger className="h-9 w-12 shrink-0 px-2 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="$and">and</SelectItem>
                <SelectItem value="$or">or</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <span className="frost-text-muted w-12 shrink-0 text-xs">{join === '$and' ? 'and' : 'or'}</span>
          )}
          <Input
            list={listId}
            value={condition.column}
            onChange={(e) => setCondition(index, { column: e.target.value })}
            placeholder="Column"
            aria-label="Column"
            className="h-9 max-w-56 min-w-0 flex-1 px-2 font-mono text-xs"
          />
          <Select
            value={condition.operator}
            onValueChange={(operator) => setCondition(index, { operator: operator as FilterOperator })}
          >
            <SelectTrigger
              className="h-9 w-auto shrink-0 gap-1 px-2 text-xs"
              aria-label="Operator"
              title={FILTER_OPERATORS.find((operator) => operator.value === condition.operator)?.title}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FILTER_OPERATORS.map((operator) => (
                <SelectItem key={operator.value} value={operator.value} title={operator.title}>
                  {operator.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            value={condition.value}
            onChange={(e) => setCondition(index, { value: e.target.value })}
            placeholder={condition.operator === 'in' ? 'a, b, c' : 'Value'}
            aria-label="Value"
            className="h-9 min-w-0 flex-1 px-2 text-xs"
          />
          {/* Just the icon, no button padding, so the inputs keep the width. */}
          <button
            type="button"
            aria-label="Remove condition"
            title="Remove condition"
            onClick={() =>
              update(conditions.length === 1 ? [emptyCondition()] : conditions.filter((_, i) => i !== index))
            }
            className="frost-text-subtle hover:text-frost-text focus-visible:ring-brand/40 shrink-0 cursor-pointer rounded focus-visible:ring-2 focus-visible:outline-none"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => update([...conditions, emptyCondition()])}
          className="text-brand inline-flex w-fit cursor-pointer items-center gap-1 text-xs font-medium"
        >
          <Plus className="size-3.5" />
          Add condition
        </button>
        <button
          type="button"
          onClick={() => setTextMode(true)}
          className="frost-text-muted hover:text-frost-text w-fit cursor-pointer text-xs"
        >
          Edit as text
        </button>
        {value ? <code className="frost-text-muted min-w-0 truncate font-mono text-xs">{value}</code> : null}
      </div>
    </div>
  );
};

export default FilterBuilder;
