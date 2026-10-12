/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { Plus, Trash2, ChevronRight, ChevronDown } from 'lucide-react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Button } from '@app/components/ui/button';

interface ParserBuilderProps {
  value: any;
  onChange: (val: any) => void;
}

const FieldEditor = ({
  field,
  onChange,
  onDelete,
}: {
  field: any;
  onChange: (val: any) => void;
  onDelete: () => void;
}) => {
  const [expanded, setExpanded] = useState(true);

  const updateField = (key: string, val: any) => {
    onChange({ ...field, [key]: val });
  };

  const hasChildren = field.type === 'object' || field.type === 'array';

  return (
    <div className="border-border/50 bg-card mt-2 flex flex-col gap-2 rounded-md border p-2 shadow-sm">
      <div className="flex items-center gap-2">
        {hasChildren ? (
          <button onClick={() => setExpanded(!expanded)} className="text-muted-foreground hover:text-foreground">
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
          onChange={(e) => {
            const newType = e.target.value;
            const newField = { ...field, type: newType };
            if (newType === 'object' && !newField.fields) {
              newField.fields = [];
            }
            if (newType === 'array' && !newField.items) {
              newField.items = { type: 'str' };
            }
            onChange(newField);
          }}
          className="bg-background border-border focus:border-primary h-7 rounded border px-1.5 text-xs focus:outline-none"
        >
          <option value="str">String</option>
          <option value="int">Integer</option>
          <option value="float">Float</option>
          <option value="bool">Boolean</option>
          <option value="object">Object</option>
          <option value="array">Array</option>
        </select>
        <button onClick={onDelete} className="text-muted-foreground hover:text-destructive p-1">
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
          {(field.fields || []).map((f: any, idx: number) => (
            <FieldEditor
              key={idx}
              field={f}
              onChange={(newF) => {
                const newFields = [...(field.fields || [])];
                newFields[idx] = newF;
                updateField('fields', newFields);
              }}
              onDelete={() => {
                const newFields = [...(field.fields || [])];
                newFields.splice(idx, 1);
                updateField('fields', newFields);
              }}
            />
          ))}
          <Button
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

  const updateRoot = (key: string, val: any) => {
    onChange({ ...value, [key]: val });
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
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-[10px]"
            onClick={() => updateRoot('fields', [...(value.fields || []), { name: '', type: 'str' }])}
          >
            <Plus size={10} /> Add Field
          </Button>
        </Label>

        <div className="flex flex-col gap-1">
          {(value.fields || []).map((f: any, idx: number) => (
            <FieldEditor
              key={idx}
              field={f}
              onChange={(newF) => {
                const newFields = [...(value.fields || [])];
                newFields[idx] = newF;
                updateRoot('fields', newFields);
              }}
              onDelete={() => {
                const newFields = [...(value.fields || [])];
                newFields.splice(idx, 1);
                updateRoot('fields', newFields);
              }}
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
