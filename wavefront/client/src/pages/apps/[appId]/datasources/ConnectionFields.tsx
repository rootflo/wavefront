import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import { cn } from '@app/lib/utils';
import { ChevronDown, Eye, EyeOff, FileUp } from 'lucide-react';
import React, { useRef, useState } from 'react';
import { ConfigField, ConfigValues } from './datasource-config';

interface ConnectionFieldsProps {
  fields: ConfigField[];
  values: ConfigValues;
  errors: Record<string, string>;
  onChange: (key: string, value: string | boolean) => void;
  /** Shown but not editable, e.g. a file storage datasource whose bucket can't change. */
  readOnly?: boolean;
}

/** A password with a show/hide toggle, so a pasted secret can be checked. */
const SecretInput = ({
  id,
  value,
  onChange,
  disabled,
  invalid,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  invalid?: boolean;
}) => {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={shown ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        autoComplete="new-password"
        className={cn('pr-10', invalid && 'border-red-500')}
      />
      <button
        type="button"
        onClick={() => setShown((visible) => !visible)}
        aria-label={shown ? 'Hide' : 'Show'}
        className="frost-text-subtle hover:text-frost-text absolute top-1/2 right-3 -translate-y-1/2 cursor-pointer"
      >
        {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
};

/** A JSON key pasted in, or read from a file the user picks. */
const JsonKeyInput = ({
  id,
  value,
  onChange,
  disabled,
  invalid,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  invalid?: boolean;
}) => {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-2">
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        spellCheck={false}
        rows={5}
        placeholder='{ "type": "service_account", "project_id": "…", "private_key": "…", "client_email": "…" }'
        className={cn('resize-y font-mono text-xs', invalid && 'border-red-500')}
      />
      {!disabled ? (
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
            <FileUp className="size-4" />
            Upload key file
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className="sr-only"
            tabIndex={-1}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (!file) return;
              const text = await file.text();
              try {
                onChange(JSON.stringify(JSON.parse(text), null, 2));
              } catch {
                // Not valid JSON: show it as it is so the error under the field explains.
                onChange(text);
              }
            }}
          />
        </div>
      ) : null}
    </div>
  );
};

/**
 * A datasource type's connection settings as labelled inputs: text, numbers, passwords with a show toggle,
 * switches, and JSON keys that can be uploaded. Less common settings fold away under "More settings".
 */
const ConnectionFields: React.FC<ConnectionFieldsProps> = ({ fields, values, errors, onChange, readOnly }) => {
  const advancedFields = fields.filter((field) => field.advanced);
  // Open the extra settings straight away if any of them already holds something worth seeing.
  const [showAdvanced, setShowAdvanced] = useState(() =>
    advancedFields.some((field) => {
      const value = values[field.key];
      return Boolean(errors[field.key]) || (typeof value === 'string' && value !== '' && value !== field.defaultValue);
    })
  );

  const renderField = (field: ConfigField) => {
    const id = `config-${field.key}`;
    const value = values[field.key];
    const error = errors[field.key];

    if (field.kind === 'boolean') {
      return (
        <div key={field.key} className={cn('flex items-start gap-3', field.wide && 'sm:col-span-2')}>
          <Switch
            id={id}
            checked={Boolean(value)}
            onCheckedChange={(checked) => onChange(field.key, checked)}
            disabled={readOnly}
            className="mt-0.5"
          />
          <div className="min-w-0">
            <Label htmlFor={id} className="cursor-pointer">
              {field.label}
            </Label>
            {field.help ? <p className="frost-text-muted mt-0.5 text-xs">{field.help}</p> : null}
          </div>
        </div>
      );
    }

    const text = typeof value === 'string' ? value : '';
    return (
      <div key={field.key} className={cn('flex min-w-0 flex-col gap-1.5', field.wide && 'sm:col-span-2')}>
        <Label htmlFor={id}>
          {field.label}
          {field.required ? <span className="ml-0.5 text-red-500">*</span> : null}
        </Label>
        {field.kind === 'password' ? (
          <SecretInput
            id={id}
            value={text}
            onChange={(next) => onChange(field.key, next)}
            disabled={readOnly}
            invalid={Boolean(error)}
          />
        ) : field.kind === 'json' ? (
          <JsonKeyInput
            id={id}
            value={text}
            onChange={(next) => onChange(field.key, next)}
            disabled={readOnly}
            invalid={Boolean(error)}
          />
        ) : (
          <Input
            id={id}
            type={field.kind === 'number' ? 'number' : 'text'}
            value={text}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            disabled={readOnly}
            className={cn(error && 'border-red-500')}
          />
        )}
        {error ? (
          <p className="text-xs text-red-500">{error}</p>
        ) : field.help ? (
          <p className="frost-text-muted text-xs">{field.help}</p>
        ) : null}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
        {fields.filter((field) => !field.advanced).map(renderField)}
      </div>
      {advancedFields.length > 0 ? (
        <div className="flex flex-col gap-4">
          <button
            type="button"
            onClick={() => setShowAdvanced((open) => !open)}
            aria-expanded={showAdvanced}
            className="text-brand inline-flex w-fit cursor-pointer items-center gap-1 text-sm font-medium"
          >
            <ChevronDown className={cn('size-4 transition-transform', showAdvanced && 'rotate-180')} />
            More settings
          </button>
          {showAdvanced ? (
            <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">{advancedFields.map(renderField)}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export default ConnectionFields;
