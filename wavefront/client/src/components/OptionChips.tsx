import { cn } from '@app/lib/utils';
import React from 'react';

interface OptionChipsProps {
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}

const OptionChips: React.FC<OptionChipsProps> = ({ options, selected, onToggle }) => (
  <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded-md border border-[#EFF0F1] bg-[#FBFBFB] p-3">
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
              ? 'border-[#282828] bg-[#282828] text-white'
              : 'border-[#EFF0F1] bg-white text-[#282828] hover:border-[#282828]'
          )}
        >
          {option}
        </button>
      );
    })}
  </div>
);

export default OptionChips;
