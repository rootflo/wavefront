import { useState } from 'react';
import { Plus, Trash2, ChevronRight, ChevronDown } from 'lucide-react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Button } from '@app/components/ui/button';

/** One field of an agent's output parser; objects nest `fields`, arrays describe their `items`. */
export interface ParserField {
  name?: string;
  type: string;
  description?: string;
  fields?: ParserField[];
  items?: ParserField;
}

/** An agent's output parser: the structured shape its answer is parsed into. */
export interface ParserSchema {
  name?: string;
  version?: string;
  description?: string;
  fields?: ParserField[];
}

interface ParserBuilderProps {
  value: ParserSchema | undefined;
  onChange: (val: ParserSchema) => void;
}

const FIELD_TYPE_OPTIONS = [
  { value: 'str', label: 'String' },
  { value: 'int', label: 'Integer' },
  { value: 'float', label: 'Float' },
  { value: 'bool', label: 'Boolean' },
  { value: 'object', label: 'Object' },
  { value: 'array', label: 'Array' },
];

const FieldEditor = ({
  field,
  onChange,
  onDelete,
}: {
  field: ParserField;
  onChange: (val: ParserField) => void;
  onDelete: () => void;
}) => {
  const [expanded, setExpanded] = useState(true);

  const updateField = <K extends keyof ParserField>(key: K, val: ParserField[K]) => {
    onChange({ ...field, [key]: val });
  };

  const handleTypeChange = (newType: string) => {
    const newField: ParserField = { ...field, type: newType };
    if (newType === 'object' && !newField.fields) {
      newField.fields = [];
    }
    if (newType === 'array' && !newField.items) {
      newField.items = { type: 'str' };
    }
    onChange(newField);
  };

  const handleNestedFieldChange = (idx: number, newF: ParserField) => {
    const newFields = [...(field.fields || [])];
    newFields[idx] = newF;
    updateField('fields', newFields);
  };

  const handleNestedFieldDelete = (idx: number) => {
    const newFields = [...(field.fields || [])];
    newFields.splice(idx, 1);
    updateField('fields', newFields);
  };

  const hasChildren = field.type === 'object' || field.type === 'array';

  return (
    <div className="border-border/50 bg-card mt-2 flex flex-col gap-2 rounded-md border p-2 shadow-sm">
      <div className="flex items-center gap-2">
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <div className="w-3.5" />
        )}
        <Input
          value={field.name || ''}
          onChange={(e) => updateField('name', e.target.value)}
          placeholder="Field name"
          className="bg-background h-7 flex-1 text-xs"
        />
        <select
          value={field.type || 'str'}
          onChange={(e) => handleTypeChange(e.target.value)}
          className="bg-background border-border focus:border-primary h-7 rounded border px-1.5 text-xs focus:outline-none"
        >
          {FIELD_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button type="button" onClick={onDelete} className="text-muted-foreground hover:text-destructive p-1">
          <Trash2 size={14} />
        </button>
      </div>

      <Input
        value={field.description || ''}
        onChange={(e) => updateField('description', e.target.value)}
        placeholder="Description"
        className="bg-background ml-6 h-7 text-[10px]"
      />

      {expanded && field.type === 'object' && (
        <div className="border-border/50 mt-1 ml-6 border-l pl-2">
          {(field.fields || []).map((f, idx) => (
            <FieldEditor
              key={idx}
              field={f}
              onChange={(newF) => handleNestedFieldChange(idx, newF)}
              onDelete={() => handleNestedFieldDelete(idx)}
            />
          ))}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-2 h-6 gap-1 px-2 text-[10px]"
            onClick={() => updateField('fields', [...(field.fields || []), { name: '', type: 'str' }])}
          >
            <Plus size={10} /> Add Object Field
          </Button>
        </div>
      )}

      {expanded && field.type === 'array' && (
        <div className="border-border/50 mt-1 ml-6 border-l pl-2">
          <div className="text-muted-foreground mb-1 text-[10px] font-semibold">Array Items Type:</div>
          <FieldEditor
            field={field.items || { type: 'str' }}
            onChange={(newItems) => updateField('items', newItems)}
            onDelete={() => updateField('items', { type: 'str' })}
          />
        </div>
      )}
    </div>
  );
};

export const ParserBuilder = ({ value, onChange }: ParserBuilderProps) => {
  if (!value) {
    return (
      <div className="bg-muted/10 border-border flex flex-col items-center justify-center rounded-md border border-dashed p-4">
        <p className="text-muted-foreground mb-2 text-[10px]">No schema defined.</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="text-xs"
          onClick={() => onChange({ name: '', version: '1.0', description: '', fields: [] })}
        >
          Initialize Schema
        </Button>
      </div>
    );
  }

  const updateRoot = <K extends keyof ParserSchema>(key: K, val: ParserSchema[K]) => {
    onChange({ ...value, [key]: val });
  };

  const handleFieldChange = (idx: number, newF: ParserField) => {
    const newFields = [...(value.fields || [])];
    newFields[idx] = newF;
    updateRoot('fields', newFields);
  };

  const handleFieldDelete = (idx: number) => {
    const newFields = [...(value.fields || [])];
    newFields.splice(idx, 1);
    updateRoot('fields', newFields);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <div className="flex gap-2">
          <div className="flex-1">
            <Label className="mb-1 block text-[10px]">Name</Label>
            <Input
              value={value.name || ''}
              onChange={(e) => updateRoot('name', e.target.value)}
              className="bg-background h-7 text-xs"
              placeholder="Schema Name"
            />
          </div>
          <div className="w-24">
            <Label className="mb-1 block text-[10px]">Version</Label>
            <Input
              value={value.version || ''}
              onChange={(e) => updateRoot('version', e.target.value)}
              className="bg-background h-7 text-xs"
              placeholder="1.0"
            />
          </div>
        </div>
        <div>
          <Label className="mb-1 block text-[10px]">Description</Label>
          <Input
            value={value.description || ''}
            onChange={(e) => updateRoot('description', e.target.value)}
            className="bg-background h-7 text-xs"
            placeholder="Schema Description"
          />
        </div>
      </div>

      <div>
        <Label className="mb-2 flex items-center justify-between text-[11px] font-semibold">
          Fields
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-[10px]"
            onClick={() => updateRoot('fields', [...(value.fields || []), { name: '', type: 'str' }])}
          >
            <Plus size={10} /> Add Field
          </Button>
        </Label>

        <div className="flex flex-col gap-1">
          {(value.fields || []).map((f, idx) => (
            <FieldEditor
              key={idx}
              field={f}
              onChange={(newF) => handleFieldChange(idx, newF)}
              onDelete={() => handleFieldDelete(idx)}
            />
          ))}
          {(!value.fields || value.fields.length === 0) && (
            <p className="text-muted-foreground border-border/50 rounded border border-dashed py-2 text-center text-[10px] italic">
              No fields defined.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
