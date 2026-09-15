import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

export const MAX_BULK_UPLOAD_FILES = 10;

export type BulkUploadFile = {
  filename: string;
  content: string;
};

export type BulkUploadParseResult<T extends object = object> = T & {
  error: string;
  label?: string;
};

const readFileAsText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });

const BulkUploadDialog = <T extends object = object>({
  isOpen,
  onOpenChange,
  title,
  description,
  maxFiles = MAX_BULK_UPLOAD_FILES,
  parseFile,
  onUpload,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  maxFiles?: number;
  parseFile: (filename: string, content: string, seen: Set<string>) => BulkUploadParseResult<T>;
  onUpload: (files: Array<T & BulkUploadFile>) => Promise<void>;
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingReadsRef = useRef(0);
  const readSessionRef = useRef(0);
  const [files, setFiles] = useState<BulkUploadFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [reading, setReading] = useState(false);
  const [limitError, setLimitError] = useState('');
  const isBusy = uploading || reading;

  const parsedFiles = useMemo(() => {
    const seen = new Set<string>();
    return files.map((file) => {
      const parsed = parseFile(file.filename, file.content, seen);
      return { ...file, ...parsed };
    });
  }, [files, parseFile]);

  const validFiles = parsedFiles.filter((file) => !file.error);

  useEffect(() => {
    if (!isOpen) {
      readSessionRef.current += 1;
      pendingReadsRef.current = 0;
      setFiles([]);
      setLimitError('');
      setUploading(false);
      setReading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [isOpen]);

  const addFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    if (uploading || pendingReadsRef.current > 0) return;

    pendingReadsRef.current += 1;
    setReading(true);
    const session = readSessionRef.current;

    try {
      const remaining = maxFiles - files.length;
      if (remaining <= 0) {
        setLimitError(`You can upload up to ${maxFiles} files at a time`);
        return;
      }

      const incoming = Array.from(fileList);
      const selected = incoming.slice(0, remaining);
      setLimitError(incoming.length > remaining ? `You can upload up to ${maxFiles} files at a time` : '');

      const nextFiles = await Promise.all(
        selected.map(async (file) => ({
          filename: file.name,
          content: await readFileAsText(file),
        }))
      );

      if (session !== readSessionRef.current) return;

      setFiles((prev) => {
        const room = maxFiles - prev.length;
        if (room <= 0) return prev;
        return [...prev, ...nextFiles.slice(0, room)];
      });
    } finally {
      pendingReadsRef.current = Math.max(0, pendingReadsRef.current - 1);
      if (pendingReadsRef.current === 0) setReading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, fileIndex) => fileIndex !== index));
    setLimitError('');
  };

  const handleUpload = async () => {
    if (validFiles.length === 0) return;
    setUploading(true);
    try {
      await onUpload(
        validFiles.map((file) => {
          const payload = { ...file } as T & BulkUploadFile & { error?: string; label?: string };
          delete payload.error;
          delete payload.label;
          return payload;
        })
      );
      onOpenChange(false);
    } finally {
      setUploading(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && isBusy) return;
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
            {files.length} of {maxFiles} files
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={isBusy || files.length >= maxFiles}
          >
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept=".yaml,.yml,text/yaml,application/x-yaml"
            multiple
            className="hidden"
            onChange={(event) => void addFiles(event.target.files)}
          />
        </div>

        {limitError ? <p className="text-sm text-red-500">{limitError}</p> : null}

        <div className="max-h-[360px] space-y-1 overflow-y-auto rounded-lg border border-[#EFF0F1] p-2">
          {parsedFiles.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-500">No files selected</p>
          ) : (
            parsedFiles.map((file, index) => (
              <div key={`${file.filename}-${index}`} className="flex items-start gap-3 rounded-md p-2 hover:bg-gray-50">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={file.filename}>
                    {file.filename}
                    {file.label ? <span className="ml-2 font-normal text-gray-500">({file.label})</span> : null}
                  </p>
                  <p className={`mt-0.5 text-xs ${file.error ? 'text-red-500' : 'text-gray-500'}`}>
                    {file.error || 'Ready to upload'}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  title="Remove"
                  disabled={isBusy}
                  onClick={() => removeFile(index)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isBusy}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => void handleUpload()}
            loading={isBusy}
            disabled={validFiles.length === 0 || isBusy}
          >
            Upload{validFiles.length > 0 ? ` (${validFiles.length})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BulkUploadDialog;
