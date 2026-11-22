import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { cn } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { Check, Folder, FolderUp, HardDrive, Loader2, X, Upload } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { PickedFile, pickedFromDrop, pickedFromInput } from './dropped-files';
import { QUEUE_ROWS_SHOWN, fileIconFor, formatBytes, locationLabelFor } from './file-storage';
import { useUploadQueue } from './useUploadQueue';

interface FileUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasourceId: string;
  /** The folder the files go into, e.g. `reports/2024/`; empty for the root. */
  targetPrefix: string;
  /** Files dropped onto the folder list, queued when the dialog opens. */
  initialFiles?: PickedFile[];
  /** Names of the files already in the target folder, to flag uploads that replace one. */
  existingFileNames: string[];
  /** Called once at least one file was uploaded, with the folder they went into. */
  onUploaded: (targetPrefix: string) => void;
}

/** Picks files and folders and uploads them, keeping their sub-folder paths. Stays open to show any failures. */
const FileUploadDialog: React.FC<FileUploadDialogProps> = ({
  open,
  onOpenChange,
  datasourceId,
  targetPrefix,
  initialFiles,
  existingFileNames,
  onUploaded,
}) => {
  const { notifyError } = useNotifyStore();
  const { uploadQueue, uploading, queueFiles, upload, clear, remove, clearFinished } = useUploadQueue(datasourceId);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const locationLabel = locationLabelFor(targetPrefix);

  // Each opening starts a new list, seeded with whatever was dropped to open it
  useEffect(() => {
    if (!open) return;
    clear();
    if (initialFiles?.length) queueFiles(initialFiles);
  }, [open, initialFiles, clear, queueFiles]);

  /** Files (and folders) dropped from the desktop, opened up into a flat list with their paths. */
  const dropFiles = async (dataTransfer: DataTransfer) => {
    try {
      queueFiles(await pickedFromDrop(dataTransfer));
    } catch {
      notifyError('Could not read the dropped files');
    }
  };

  const handleUpload = async () => {
    const { uploaded, failed } = await upload(targetPrefix);
    if (uploaded > 0) onUploaded(targetPrefix);
    // Close when everything went up; stay open to show what failed otherwise.
    if (failed === 0) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !uploading && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload files</DialogTitle>
          <DialogDescription className="flex items-center gap-1.5">
            Into
            <span className="frost-text inline-flex min-w-0 items-center gap-1 font-medium">
              {targetPrefix ? (
                <Folder className="size-3.5 shrink-0 text-amber-500" />
              ) : (
                <HardDrive className="size-3.5 shrink-0" />
              )}
              <span className="truncate font-mono text-xs">{locationLabel}</span>
            </span>
          </DialogDescription>
        </DialogHeader>

        {/* Drop files here or click to pick; the folder open in the browser is where they go. */}
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void dropFiles(e.dataTransfer);
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors',
            dragging ? 'border-brand bg-brand/10' : 'border-frost-border hover:border-brand/50 hover:bg-frost-glass'
          )}
        >
          <span className="bg-brand/12 text-brand flex size-10 items-center justify-center rounded-xl">
            <Upload className="size-5" />
          </span>
          <span className="frost-text text-sm font-medium">Drop files or folders here, or click to choose files</span>
          <span className="frost-text-muted text-xs">Folders keep their sub-folders.</span>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="sr-only"
            disabled={uploading}
            onChange={(e) => {
              if (e.target.files) queueFiles(pickedFromInput(e.target.files));
              e.target.value = '';
            }}
          />
        </label>
        <div className="-mt-1 flex items-center justify-center gap-2 text-xs">
          <span className="frost-text-muted">or</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={uploading}
            onClick={() => folderInputRef.current?.click()}
          >
            <FolderUp className="size-4" />
            Choose a folder
          </Button>
          {/* webkitdirectory isn't in React's input types, so it's set on the element itself. */}
          <input
            ref={(element) => {
              folderInputRef.current = element;
              element?.setAttribute('webkitdirectory', '');
            }}
            type="file"
            multiple
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              if (e.target.files) queueFiles(pickedFromInput(e.target.files));
              e.target.value = '';
            }}
          />
        </div>

        {uploadQueue.length > 0 ? (
          <div className="frost-text-muted flex items-center justify-between gap-2 text-xs">
            <span>
              {uploadQueue.length} file{uploadQueue.length === 1 ? '' : 's'} ·{' '}
              {formatBytes(uploadQueue.reduce((total, item) => total + item.file.size, 0))}
              {uploadQueue.some((item) => item.status === 'done')
                ? ` · ${uploadQueue.filter((item) => item.status === 'done').length} uploaded`
                : ''}
            </span>
            {!uploading ? (
              <button type="button" onClick={clearFinished} className="hover:text-frost-text cursor-pointer">
                Clear
              </button>
            ) : null}
          </div>
        ) : null}
        {uploadQueue.length > 0 ? (
          <ul className="divide-frost-border border-frost-border max-h-60 divide-y overflow-y-auto rounded-lg border">
            {/* A whole folder can be thousands of files; the list shows the first few hundred. */}
            {uploadQueue.slice(0, QUEUE_ROWS_SHOWN).map((item, index) => {
              // Only a file landing directly in the open folder can clash with what's listed there.
              const replaces = !item.relativePath.includes('/') && existingFileNames.includes(item.file.name);
              const Icon = fileIconFor(item.file.name);
              return (
                <li key={`${item.relativePath}-${index}`} className="flex items-center gap-3 px-3 py-2">
                  <Icon className="frost-text-muted size-4 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="frost-text truncate text-sm" title={item.relativePath}>
                      {item.relativePath}
                    </p>
                    <p
                      className={cn(
                        'truncate text-xs',
                        item.status === 'failed'
                          ? 'text-red-500'
                          : replaces && item.status === 'pending'
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'frost-text-muted'
                      )}
                    >
                      {item.status === 'failed'
                        ? item.error
                        : item.status === 'done'
                          ? 'Uploaded'
                          : item.status === 'uploading'
                            ? 'Uploading…'
                            : replaces
                              ? `${formatBytes(item.file.size)} · replaces the file with this name`
                              : formatBytes(item.file.size)}
                    </p>
                  </div>
                  {item.status === 'uploading' ? (
                    <Loader2 className="text-brand size-4 shrink-0 animate-spin" />
                  ) : item.status === 'done' ? (
                    <Check className="size-4 shrink-0 text-emerald-600" />
                  ) : (
                    <button
                      type="button"
                      aria-label={`Remove ${item.file.name}`}
                      disabled={uploading}
                      onClick={() => remove(index)}
                      className="frost-text-subtle hover:text-frost-text shrink-0 cursor-pointer"
                    >
                      <X className="size-4" />
                    </button>
                  )}
                </li>
              );
            })}
            {uploadQueue.length > QUEUE_ROWS_SHOWN ? (
              <li className="frost-text-muted px-3 py-2 text-xs">
                and {(uploadQueue.length - QUEUE_ROWS_SHOWN).toLocaleString()} more
                {uploadQueue.slice(QUEUE_ROWS_SHOWN).some((item) => item.status === 'failed')
                  ? ', some of which failed'
                  : ''}
              </li>
            ) : null}
          </ul>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={uploading}>
            {uploadQueue.some((item) => item.status === 'done') ? 'Close' : 'Cancel'}
          </Button>
          <Button
            onClick={() => void handleUpload()}
            loading={uploading}
            disabled={uploading || !uploadQueue.some((item) => item.status === 'pending' || item.status === 'failed')}
          >
            {uploadQueue.some((item) => item.status === 'failed')
              ? 'Retry failed'
              : `Upload${uploadQueue.length > 0 ? ` ${uploadQueue.length} file${uploadQueue.length === 1 ? '' : 's'}` : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default FileUploadDialog;
