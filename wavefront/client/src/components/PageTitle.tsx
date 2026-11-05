import { cn } from '@app/lib/utils';
import React from 'react';

interface PageTitleProps {
  className?: string;
  /** While the page's resource loads, a placeholder bar the height of the text stands in for it. */
  loading?: boolean;
  children?: React.ReactNode;
}

/** The page heading, the same on listing and detail pages so moving between them doesn't shift the title. */
const PageTitle = ({ className, loading, children }: PageTitleProps) => (
  <h1
    className={cn(
      'frost-text min-w-0 truncate text-2xl leading-tight font-bold tracking-tight md:text-[28px]',
      className
    )}
  >
    {loading ? (
      <span
        aria-label="Loading"
        className="bg-primary/10 inline-block h-[0.85em] w-48 animate-pulse rounded-md align-middle md:w-64"
      />
    ) : (
      children
    )}
  </h1>
);

export default PageTitle;
