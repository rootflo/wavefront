import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@app/lib/utils';

const alertVariants = cva(
  'relative w-full rounded-lg border px-4 py-3 text-sm backdrop-blur-md shadow-[var(--frost-inset-shadow)] [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg~*]:pl-7',
  {
    variants: {
      variant: {
        default: 'frost-glass frost-text border-frost-border ring-1 ring-frost-border [&>svg]:text-frost-text',
        destructive:
          'border-rose-500/30 bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/15 dark:border-rose-400/25 dark:bg-rose-500/10 dark:text-rose-300 [&>svg]:text-rose-600 dark:[&>svg]:text-rose-400',
        success:
          'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/15 dark:border-emerald-400/25 dark:bg-emerald-500/10 dark:text-emerald-300 [&>svg]:text-emerald-600 dark:[&>svg]:text-emerald-400',
        info: 'border-brand/25 bg-brand/8 text-sky-900 ring-1 ring-brand/10 dark:border-frost-border dark:bg-frost-glass dark:text-frost-text dark:ring-frost-border [&>svg]:text-brand dark:[&>svg]:text-frost-text-muted',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
));
Alert.displayName = 'Alert';

const AlertTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h5 ref={ref} className={cn('mb-1 leading-none font-medium tracking-tight', className)} {...props} />
  )
);
AlertTitle.displayName = 'AlertTitle';

const AlertDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('text-sm [&_p]:leading-relaxed', className)} {...props} />
  )
);
AlertDescription.displayName = 'AlertDescription';

export { Alert, AlertTitle, AlertDescription };
