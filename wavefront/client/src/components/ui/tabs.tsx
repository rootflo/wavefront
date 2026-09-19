import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';

import { cn } from '@app/lib/utils';

const Tabs = TabsPrimitive.Root;

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      'frost-card frost-text-muted ring-frost-border inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border p-1 ring-1',
      className
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'frost-text-muted focus-visible:ring-brand/30 data-[state=active]:bg-frost-dialog data-[state=active]:text-frost-text relative inline-flex h-full cursor-pointer items-center justify-center rounded-md px-3 py-1 text-[13px] font-medium tracking-normal whitespace-nowrap normal-case transition-all focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 data-[state=active]:font-semibold data-[state=active]:shadow-[var(--frost-inset-shadow)] data-[state=active]:[&_[data-tab-underline]]:opacity-100',
      className
    )}
    {...props}
  >
    <span className="relative inline-flex flex-col items-center">
      {children}
      <span
        data-tab-underline
        aria-hidden
        className="bg-brand absolute top-[calc(100%+2px)] left-1/2 h-0.5 w-1/2 -translate-x-1/2 rounded-full opacity-0 transition-opacity"
      />
    </span>
  </TabsPrimitive.Trigger>
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'ring-offset-background focus-visible:ring-ring mt-2 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none',
      className
    )}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
