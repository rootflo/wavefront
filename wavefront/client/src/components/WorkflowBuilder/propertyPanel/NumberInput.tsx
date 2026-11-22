import React from 'react';
import { Input } from '@app/components/ui/input';

interface NumberInputProps {
  value: unknown;
  // Called with a number, or undefined when the field is cleared. Never called with a partial entry such as '0.'
  onChange: (value: number | undefined) => void;
  min?: number;
  max?: number;
  step?: number | string;
  placeholder?: string;
  className?: string;
}

const formatValue = (value: unknown): string => (value === undefined || value === null ? '' : String(value));

const toNumber = (value: unknown): number | undefined => {
  if (value === undefined || value === null || value === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};

// Number field that keeps the typed text locally, so '0', '0.' and '-' stay visible while typing,
// and only commits complete numbers (0 is a valid value, not an empty field).
export const NumberInput = ({ value, onChange, min, max, step, placeholder, className }: NumberInputProps) => {
  const [text, setText] = React.useState(() => formatValue(value));
  const committed = React.useRef<number | undefined>(toNumber(value));

  // Adopt values that change from outside this field (another panel, YAML re-parse)
  React.useEffect(() => {
    const next = toNumber(value);
    if (next !== committed.current) {
      committed.current = next;
      setText(formatValue(value));
    }
  }, [value]);

  const handleChange = (raw: string) => {
    setText(raw);
    if (raw.trim() === '') {
      committed.current = undefined;
      onChange(undefined);
      return;
    }
    const n = Number(raw);
    if (Number.isFinite(n) && !raw.trim().endsWith('.')) {
      committed.current = n;
      onChange(n);
    }
  };

  return (
    <Input
      type="number"
      inputMode="decimal"
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      value={text}
      onChange={(e) => handleChange(e.target.value)}
      className={className}
    />
  );
};
