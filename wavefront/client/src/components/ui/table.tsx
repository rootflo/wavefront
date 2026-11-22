import * as React from 'react';

import { cn } from '@app/lib/utils';

interface TableProps extends React.HTMLAttributes<HTMLTableElement> {
  /** On a phone, show each row as a card (label above value) instead of a scrolling table. */
  cards?: boolean;
}

const Table = React.forwardRef<HTMLTableElement, TableProps>(({ className, cards, ...props }, ref) => {
  const tableRef = React.useRef<HTMLTableElement | null>(null);

  // The card layout labels each value with its column header, so copy the header text onto every cell.
  React.useLayoutEffect(() => {
    const table = tableRef.current;
    if (!cards || !table) return;
    const headers = Array.from(table.querySelectorAll('thead th')).map((th) => th.textContent?.trim() ?? '');
    table.querySelectorAll('tbody tr').forEach((row) => {
      Array.from(row.children).forEach((cell, index) => {
        const label = (cell as HTMLTableCellElement).colSpan > 1 ? '' : (headers[index] ?? '');
        if (cell.getAttribute('data-label') !== label) cell.setAttribute('data-label', label);
      });
    });
  });

  const setRefs = (node: HTMLTableElement | null) => {
    tableRef.current = node;
    if (typeof ref === 'function') ref(node);
    else if (ref) ref.current = node;
  };

  return (
    <div className="relative w-full bg-transparent">
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />
      <table
        ref={setRefs}
        data-cards={cards ? '' : undefined}
        className={cn('relative w-full min-w-[36rem] caption-bottom text-sm lg:min-w-0', className)}
        {...props}
      />
    </div>
  );
});
Table.displayName = 'Table';

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead
      ref={ref}
      className={cn(
        '[&_th]:bg-frost-glass z-10 [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:shadow-[inset_0_-1px_0_0_var(--frost-border)] [&_th]:backdrop-blur-md [&_tr]:border-b-0',
        className
      )}
      {...props}
    />
  )
);
TableHeader.displayName = 'TableHeader';

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn('bg-transparent [&_tr:last-child]:border-0', className)} {...props} />
  )
);
TableBody.displayName = 'TableBody';

const TableFooter = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tfoot
      ref={ref}
      className={cn(
        'border-frost-border bg-frost-glass border-t font-medium backdrop-blur-md [&>tr]:last:border-b-0',
        className
      )}
      {...props}
    />
  )
);
TableFooter.displayName = 'TableFooter';

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn(
        'border-frost-border hover:bg-frost-glass data-[state=selected]:bg-frost-glass-strong border-b transition-colors',
        className
      )}
      {...props}
    />
  )
);
TableRow.displayName = 'TableRow';

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        'frost-text-muted h-10 px-3 text-left align-middle text-[11px] font-medium tracking-normal normal-case [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]',
        className
      )}
      {...props}
    />
  )
);
TableHead.displayName = 'TableHead';

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td
      ref={ref}
      className={cn(
        'frost-text p-3 align-middle text-[13px] tracking-normal normal-case [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]',
        className
      )}
      {...props}
    />
  )
);
TableCell.displayName = 'TableCell';

const TableCaption = React.forwardRef<HTMLTableCaptionElement, React.HTMLAttributes<HTMLTableCaptionElement>>(
  ({ className, ...props }, ref) => (
    <caption
      ref={ref}
      className={cn('frost-text-muted mt-4 text-[13px] tracking-normal normal-case', className)}
      {...props}
    />
  )
);
TableCaption.displayName = 'TableCaption';

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
