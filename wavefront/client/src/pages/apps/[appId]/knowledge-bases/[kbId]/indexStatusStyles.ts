import { IndexStatus } from '@app/api/knowledge-base-service';

const PENDING = {
  className: 'text-yellow-600 dark:text-yellow-400',
  pillClassName:
    'border-yellow-300 bg-yellow-100 text-yellow-800 dark:border-yellow-800 dark:bg-yellow-950/50 dark:text-yellow-300',
  dotClassName: 'bg-yellow-500',
};

// Labels and colours for each indexing state: green once indexed, red when it
// failed, yellow while still queued or indexing.
export const INDEX_STATUS_STYLES: Record<
  IndexStatus | 'NOT_TRACKED',
  { label: string; className: string; pillClassName: string; dotClassName: string }
> = {
  QUEUED: { label: 'Queued', ...PENDING },
  IN_PROGRESS: { label: 'Indexing', ...PENDING, dotClassName: 'bg-yellow-500 animate-pulse' },
  COMPLETE: {
    label: 'Indexed',
    className: 'text-green-600 dark:text-green-400',
    pillClassName:
      'border-green-300 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-950/50 dark:text-green-300',
    dotClassName: 'bg-green-500',
  },
  FAILED: {
    label: 'Failed',
    className: 'text-red-600 dark:text-red-400',
    pillClassName: 'border-red-300 bg-red-100 text-red-800 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300',
    dotClassName: 'bg-red-500',
  },
  NOT_TRACKED: {
    label: 'Not tracked',
    className: 'frost-text-muted',
    pillClassName: 'frost-text-muted border-frost-border',
    dotClassName: 'bg-gray-400',
  },
};
