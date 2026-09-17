import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import * as React from 'react';

import { cn } from '@app/lib/utils';
import { Spinner } from './spinner';

const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md text-[13px] font-medium tracking-normal whitespace-nowrap normal-case transition-all outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 focus-visible:ring-2 focus-visible:ring-sky-400/30",
  {
    variants: {
      variant: {
        default:
          'border border-brand/40 bg-brand text-white shadow-[0_1px_0_rgba(255,255,255,0.25)_inset] hover:bg-brand-hover dark:border-white/12 dark:bg-white/10 dark:text-slate-100 dark:shadow-[0_1px_0_rgba(255,255,255,0.14)_inset] dark:ring-1 dark:ring-white/10 dark:backdrop-blur-md dark:hover:bg-white/16 dark:hover:text-white',
        destructive:
          'border border-rose-500/20 bg-rose-500/90 text-white shadow-[0_1px_0_rgba(255,255,255,0.2)_inset] hover:bg-rose-500 focus-visible:ring-rose-400/30',
        outline: 'frost-control border border-frost-border ring-1 ring-frost-border hover:bg-frost-glass-strong',
        secondary:
          'border border-frost-border bg-frost-glass text-frost-text shadow-[var(--frost-inset-shadow)] ring-1 ring-frost-border backdrop-blur-md hover:bg-frost-glass-strong',
        ghost: 'frost-text-muted hover:bg-frost-glass-strong hover:text-frost-text',
        'ghost-destructive':
          'text-red-500 hover:bg-red-50/80 hover:text-red-700 focus-visible:ring-rose-400/30 dark:hover:bg-red-500/15 dark:hover:text-red-400',
        link: 'text-brand underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2 has-[>svg]:px-3',
        sm: 'h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5',
        lg: 'h-10 rounded-md px-6 has-[>svg]:px-4',
        icon: 'size-9',
        'icon-sm': 'size-8',
        'icon-xs': 'size-7',
        'icon-lg': 'size-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  disabled = false,
  loading = false,
  children,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    loading?: boolean;
  }) {
  const Comp = asChild ? Slot : 'button';

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </Comp>
  );
}

export { Button, buttonVariants };
