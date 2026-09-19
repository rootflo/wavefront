import * as React from 'react';

import { cn } from '@app/lib/utils';

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          'frost-control ring-frost-border placeholder:text-frost-text-subtle focus-visible:border-brand/40 focus-visible:ring-brand/25 flex min-h-[60px] w-full rounded-md border px-3 py-2 text-[13px] tracking-normal normal-case ring-1 transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Textarea.displayName = 'Textarea';

export { Textarea };
