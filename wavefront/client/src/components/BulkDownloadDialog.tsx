import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { useEffect, useMemo, useState } from 'react';

const BulkDownloadDialog = <T,>({
  isOpen,
  onOpenChange,
  title,
  description,
  emptyLabel,
  items,
  getItemId,
  getItemLabel,
  onDownload,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  emptyLabel: string;
  items: T[];
  getItemId: (item: T) => string;
  getItemLabel: (item: T) => string;
  onDownload: (items: T[]) => Promise<void>;
}) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [downloading, setDownloading] = useState(false);

  const sortedItems = useMemo(
    () => [...items].sort((a, b) => getItemLabel(a).localeCompare(getItemLabel(b), undefined, { sensitivity: 'base' })),
    [items, getItemLabel]
  );

  useEffect(() => {
    if (isOpen) setSelectedIds([]);
  }, [isOpen]);

  const toggleId = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]));
  };

  const handleDownload = async () => {
    const selected = sortedItems.filter((item) => selectedIds.includes(getItemId(item)));
    if (selected.length === 0) return;

    setDownloading(true);
    try {
      await onDownload(selected);
      onOpenChange(false);
    } finally {
      setDownloading(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && downloading) return;
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600">
            {selectedIds.length} of {sortedItems.length} selected
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSelectedIds(sortedItems.map((item) => getItemId(item)))}
              disabled={downloading || sortedItems.length === 0}
            >
              Select all
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSelectedIds([])}
              disabled={downloading || selectedIds.length === 0}
            >
              Clear all
            </Button>
          </div>
        </div>

        <div className="max-h-[360px] space-y-1 overflow-y-auto rounded-lg border border-[#EFF0F1] p-2">
          {sortedItems.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-500">{emptyLabel}</p>
          ) : (
            sortedItems.map((item) => {
              const id = getItemId(item);
              const label = getItemLabel(item);
              return (
                <div key={id} className="flex items-center gap-3 rounded-md p-2 hover:bg-gray-50">
                  <Checkbox
                    id={`download-${id}`}
                    checked={selectedIds.includes(id)}
                    disabled={downloading}
                    onCheckedChange={() => toggleId(id)}
                  />
                  <label
                    htmlFor={`download-${id}`}
                    className="min-w-0 flex-1 cursor-pointer truncate text-sm"
                    title={label}
                  >
                    {label}
                  </label>
                </div>
              );
            })
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={downloading}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => void handleDownload()}
            loading={downloading}
            disabled={selectedIds.length === 0}
          >
            Download
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BulkDownloadDialog;
