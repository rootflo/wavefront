import * as React from 'react';

import { cn } from '@app/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'frost-control ring-frost-border file:text-frost-text placeholder:text-frost-text-subtle focus-visible:border-brand/40 focus-visible:ring-brand/25 flex h-9 w-full rounded-md border px-3 py-1 text-[13px] tracking-normal normal-case ring-1 transition-colors file:border-0 file:bg-transparent file:text-[13px] file:font-medium focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = 'Input';

export { Input };
