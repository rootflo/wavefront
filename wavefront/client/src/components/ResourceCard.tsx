import { Button } from '@app/components/ui/button';
import { copyToClipboard, formatAppName } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { Check, Copy, Pencil, Trash2 } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';

export interface ResourceCardMetadata {
  label: string;
  value: string;
  className?: string;
  isMono?: boolean;
  isCopyable?: boolean;
}

interface ResourceCardProps {
  title: string;
  description?: string;
  metadata: ResourceCardMetadata[];
  onClick: () => void;
  onDeleteClick: (e: React.MouseEvent) => void;
  onEditClick?: (e: React.MouseEvent) => void;
  deleteTitle?: string;
  editTitle?: string;
}

const cardShell =
  'frost-card group relative cursor-pointer overflow-hidden rounded-xl border p-5 ring-1 ring-frost-border transition-all duration-300 hover:-translate-y-0.5 hover:bg-frost-glass-strong';

const cardIconButtonClass = 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100';

const ResourceCard: React.FC<ResourceCardProps> = ({
  title,
  description,
  metadata,
  onClick,
  onDeleteClick,
  onEditClick,
  deleteTitle = 'Delete',
  editTitle = 'Edit',
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async (e: React.MouseEvent, value: string, index: number) => {
    e.stopPropagation();
    const copied = await copyToClipboard(value);
    if (!copied) {
      notifyError('Failed to copy to clipboard');
      return;
    }
    notifySuccess('Copied to clipboard');
    setCopiedIndex(index);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => {
      setCopiedIndex(null);
    }, 2000);
  };

  return (
    <div onClick={onClick} className={cardShell}>
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />

      <div className="relative mb-3 flex items-start justify-between gap-3">
        <h3 className="frost-text group-hover:text-brand overflow-hidden pr-2 text-[15px] font-medium tracking-normal text-ellipsis normal-case transition-colors dark:group-hover:text-slate-100">
          {formatAppName(title)}
        </h3>
        <div className="flex shrink-0 items-center gap-1">
          {onEditClick ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              title={editTitle}
              aria-label={editTitle}
              className={cardIconButtonClass}
              onClick={onEditClick}
            >
              <Pencil className="size-3.5" />
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost-destructive"
            size="icon-xs"
            title={deleteTitle}
            aria-label={deleteTitle}
            className={cardIconButtonClass}
            onClick={onDeleteClick}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      {description ? (
        <p className="frost-text-muted relative mb-4 line-clamp-2 text-[13px] leading-relaxed font-normal tracking-normal normal-case">
          {description}
        </p>
      ) : null}

      <div className="relative space-y-2">
        {metadata.map((item, index) => {
          const valueClassName = `truncate rounded-md px-2 py-1 font-medium tracking-normal normal-case ${
            item.className ||
            (item.isMono
              ? 'frost-control frost-text ring-frost-border font-mono ring-1'
              : 'frost-control frost-text ring-frost-border ring-1')
          }`;

          return (
            <div key={index} className="flex items-center justify-between gap-3 text-[11px]">
              <span className="frost-text-muted shrink-0 font-medium tracking-normal normal-case">{item.label}</span>
              {item.isCopyable ? (
                <div className="flex max-w-[60%] min-w-0 items-center gap-0.5">
                  <span className={`min-w-0 ${valueClassName}`}>{item.value}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    title={copiedIndex === index ? 'Copied to clipboard' : 'Copy to clipboard'}
                    aria-label={copiedIndex === index ? 'Copied to clipboard' : 'Copy to clipboard'}
                    className={`size-5 shrink-0 ${copiedIndex === index ? 'text-emerald-600' : 'frost-text-muted'}`}
                    onClick={(e) => void handleCopy(e, item.value, index)}
                  >
                    {copiedIndex === index ? <Check className="size-3" /> : <Copy className="size-3" />}
                  </Button>
                </div>
              ) : (
                <span className={`max-w-[60%] ${valueClassName}`}>{item.value}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

interface ResourceCardSkeletonProps {
  showDescription?: boolean;
  metadataCount?: number;
}

export const ResourceCardSkeleton: React.FC<ResourceCardSkeletonProps> = ({
  showDescription = false,
  metadataCount = 2,
}) => {
  return (
    <div className="frost-card animate-fade-in ring-frost-border rounded-xl border p-5 ring-1">
      <div className="mb-3 flex items-start justify-between">
        <div className="bg-frost-text-subtle/20 h-5 w-32 animate-pulse rounded-md" />
        <div className="flex items-center gap-2">
          <div className="bg-frost-text-subtle/20 h-4 w-4 rounded" />
          <div className="bg-frost-text-subtle/20 h-4 w-4 rounded" />
        </div>
      </div>
      {showDescription ? (
        <div className="mb-4 space-y-2">
          <div className="bg-frost-text-subtle/20 h-3.5 w-full animate-pulse rounded" />
          <div className="bg-frost-text-subtle/20 h-3.5 w-3/4 animate-pulse rounded" />
        </div>
      ) : null}
      <div className="space-y-2">
        {Array.from({ length: metadataCount }).map((_, index) => (
          <div key={index} className="flex items-center justify-between text-xs">
            <div className="bg-frost-text-subtle/20 h-3 w-16 animate-pulse rounded" />
            <div className="bg-frost-text-subtle/20 h-5 w-20 animate-pulse rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
};

export default ResourceCard;
