import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import { cn } from '@app/lib/utils';
import { Info } from 'lucide-react';
import React from 'react';

interface FieldHelpProps {
  children: React.ReactNode;
  ariaLabel: string;
  side?: 'top' | 'right' | 'bottom' | 'left';
  contentClassName?: string;
}

const FieldHelp: React.FC<FieldHelpProps> = ({ children, ariaLabel, side = 'top', contentClassName = 'max-w-xs' }) => (
  <TooltipProvider delayDuration={200}>
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex cursor-pointer text-[#878787] hover:text-[#555555]"
          aria-label={ariaLabel}
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side={side} className={cn(contentClassName)}>
        {children}
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

export default FieldHelp;
