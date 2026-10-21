import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { EntityVersion } from '@app/types/version';
import React from 'react';

interface EditorVersionSelectProps {
  versions: EntityVersion[];
  value?: number;
  disabled?: boolean;
  onChange: (version: number) => void;
}

// Picks which workflow version the editor shows and saves to. View and edit only: promoting and deleting
// versions stays on the workflow page.
const EditorVersionSelect: React.FC<EditorVersionSelectProps> = ({ versions, value, disabled, onChange }) => (
  <Select
    value={value !== undefined ? String(value) : ''}
    onValueChange={(v) => onChange(Number(v))}
    disabled={disabled}
  >
    <SelectTrigger aria-label="Workflow version" className="bg-background h-7 w-[8.5rem] text-xs">
      <SelectValue placeholder="Version" />
    </SelectTrigger>
    <SelectContent>
      {[...versions]
        .filter((v) => !v.is_deleted)
        .sort((a, b) => a.version - b.version)
        .map((v) => (
          <SelectItem key={v.id} value={String(v.version)} className="text-xs">
            v{v.version}
            {v.is_current ? ' (current)' : ''}
          </SelectItem>
        ))}
    </SelectContent>
  </Select>
);

export default EditorVersionSelect;
