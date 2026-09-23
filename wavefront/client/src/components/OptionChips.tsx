import { cn } from '@app/lib/utils';
import React from 'react';

interface OptionChipsProps {
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}

const OptionChips: React.FC<OptionChipsProps> = ({ options, selected, onToggle }) => (
  <div className="frost-glass border-frost-border flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded-md border p-3">
    {options.map((option) => {
      const isSelected = selected.includes(option);
      return (
        <button
          key={option}
          type="button"
          aria-pressed={isSelected}
          onClick={() => onToggle(option)}
          className={cn(
            'rounded-full border px-3 py-1 text-xs transition-colors',
            isSelected
              ? 'border-frost-text bg-frost-text text-white dark:bg-white dark:text-slate-900'
              : 'frost-glass-strong frost-text border-frost-border hover:border-frost-text'
          )}
        >
          {option}
        </button>
      );
    })}
  </div>
);

export default OptionChips;
