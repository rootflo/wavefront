import { IndexStatus } from '@app/api/knowledge-base-service';
import { cn } from '@app/lib/utils';
import React from 'react';
import { INDEX_STATUS_STYLES } from './indexStatusStyles';

interface IndexStatusPillProps {
  status: IndexStatus | null | undefined;
  error?: string | null;
}

/** A document's indexing state as a coloured pill; failed ones show the error on hover. */
const IndexStatusPill: React.FC<IndexStatusPillProps> = ({ status, error }) => {
  const style = INDEX_STATUS_STYLES[status ?? 'NOT_TRACKED'];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        style.pillClassName
      )}
      title={error || undefined}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', style.dotClassName)} />
      {style.label}
    </span>
  );
};

export default IndexStatusPill;
