import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { copyToClipboard, downloadBlobFile, extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { DatasourceFileEntry } from '@app/types/datasource';
import { ChevronRight, Copy, Download, Folder, RefreshCw, Trash2, Upload } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

interface FileStoragePanelProps {
  datasourceId: string;
}

type PreviewKind = 'image' | 'video' | 'text' | 'unsupported';

type FilePreviewState = {
  entry: DatasourceFileEntry;
  kind: PreviewKind;
  objectUrl?: string;
  text?: string;
  contentType: string;
  sizeBytes: number;
};

type FolderEntry = {
  kind: 'folder';
  name: string;
  /** Prefix used for list API / navigation, with trailing slash when non-root */
  prefix: string;
};

type FileRow = {
  kind: 'file';
  entry: DatasourceFileEntry;
};

type BrowserRow = FolderEntry | FileRow;

const TEXT_PREVIEW_MAX_BYTES = 512 * 1024;
const PAGE_SIZE = 50;
/** Cap recursive pages under a prefix so a huge bucket cannot hang the UI. */
const MAX_LIST_PAGES = 40;

/** Blob responses hide the JSON error body; read it back out for the message. */
const getDownloadErrorMessage = async (error: unknown): Promise<string | undefined> => {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text()) as { meta?: { error?: string } };
      return body.meta?.error;
    } catch {
      return undefined;
    }
  }
  return extractErrorMessage(error);
};

const mimeTypeOf = (contentType: string | undefined, blobType: string) =>
  (contentType || blobType || 'application/octet-stream').split(';')[0].trim().toLowerCase();

const previewKindFor = (mime: string): PreviewKind => {
  if (mime.startsWith('image/') && mime !== 'image/svg+xml') return 'image';
  if (mime.startsWith('video/')) return 'video';
  if (
    mime.startsWith('text/') ||
    mime === 'application/json' ||
    mime === 'application/xml' ||
    mime === 'application/javascript' ||
    mime.endsWith('+json') ||
    mime.endsWith('+xml')
  ) {
    return 'text';
  }
  return 'unsupported';
};

/** Normalize to '' or 'a/b/' (no leading slash). */
const normalizeDirPrefix = (prefix: string): string => {
  const trimmed = prefix.replace(/^\/+/, '').replace(/\/+$/, '');
  return trimmed ? `${trimmed}/` : '';
};

/** API list prefix: no trailing slash (matches backend tests / storage prefix join). */
const listApiPrefix = (dirPrefix: string): string => dirPrefix.replace(/\/+$/, '');

const breadcrumbSegments = (dirPrefix: string): { label: string; prefix: string }[] => {
  const trimmed = dirPrefix.replace(/^\/+|\/+$/g, '');
  if (!trimmed) return [];
  const parts = trimmed.split('/');
  return parts.map((label, index) => ({
    label,
    prefix: `${parts.slice(0, index + 1).join('/')}/`,
  }));
};

/**
 * Collapse a recursive flat key list into immediate folders + files under `dirPrefix`.
 */
const buildBrowserRows = (files: DatasourceFileEntry[], dirPrefix: string): BrowserRow[] => {
  const prefix = normalizeDirPrefix(dirPrefix);
  const folders = new Map<string, FolderEntry>();
  const fileRows: FileRow[] = [];

  for (const entry of files) {
    const relative = entry.relative_path.replace(/^\/+/, '');
    if (prefix && !relative.startsWith(prefix) && relative !== prefix.slice(0, -1)) {
      continue;
    }

    const remainder = prefix ? relative.slice(prefix.length) : relative;
    if (!remainder) continue;

    const slash = remainder.indexOf('/');
    if (slash === -1) {
      fileRows.push({ kind: 'file', entry });
      continue;
    }

    const folderName = remainder.slice(0, slash);
    if (!folders.has(folderName)) {
      folders.set(folderName, {
        kind: 'folder',
        name: folderName,
        prefix: `${prefix}${folderName}/`,
      });
    }
  }

  const folderRows = [...folders.values()].sort((a, b) => a.name.localeCompare(b.name));
  fileRows.sort((a, b) => a.entry.name.localeCompare(b.entry.name));
  return [...folderRows, ...fileRows];
};

const FileStoragePanel: React.FC<FileStoragePanelProps> = ({ datasourceId }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewObjectUrlRef = useRef<string | null>(null);

  /** Current directory: '' root, or 'docs/reports/' */
  const [currentPrefix, setCurrentPrefix] = useState('');
  const [files, setFiles] = useState<DatasourceFileEntry[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [listTruncated, setListTruncated] = useState(false);

  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadPath, setUploadPath] = useState('');
  const [uploading, setUploading] = useState(false);

  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);
  const [filePendingDelete, setFilePendingDelete] = useState<DatasourceFileEntry | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [preview, setPreview] = useState<FilePreviewState | null>(null);
  const [previewLoadingPath, setPreviewLoadingPath] = useState<string | null>(null);

  const loadFiles = useCallback(
    async (dirPrefix = currentPrefix) => {
      setLoadingFiles(true);
      setListTruncated(false);
      try {
        const apiPrefix = listApiPrefix(dirPrefix);
        const collected: DatasourceFileEntry[] = [];
        let page = 1;
        let hasMore = true;

        while (hasMore && page <= MAX_LIST_PAGES) {
          const response = await floConsoleService.datasourcesService.listFiles(datasourceId, {
            prefix: apiPrefix || undefined,
            page_number: page,
            page_size: PAGE_SIZE,
          });
          const data = response.data?.data;
          collected.push(...(data?.files ?? []));
          hasMore = Boolean(data?.has_next_page);
          page += 1;
        }

        if (hasMore) {
          setListTruncated(true);
        }
        setFiles(collected);
      } catch (error) {
        notifyError(extractErrorMessage(error) || 'Failed to list files');
        setFiles([]);
      } finally {
        setLoadingFiles(false);
      }
    },
    [currentPrefix, datasourceId, notifyError]
  );

  useEffect(() => {
    void loadFiles(currentPrefix);
  }, [currentPrefix, loadFiles]);

  const browserRows = useMemo(() => buildBrowserRows(files, currentPrefix), [files, currentPrefix]);
  const crumbs = useMemo(() => breadcrumbSegments(currentPrefix), [currentPrefix]);

  const clearPreview = useCallback(() => {
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setPreview(null);
    setPreviewLoadingPath(null);
  }, []);

  useEffect(() => () => clearPreview(), [clearPreview]);

  const resetUploadForm = (dirPrefix = currentPrefix) => {
    setFile(null);
    setUploadPath(normalizeDirPrefix(dirPrefix));
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const openUploadDialog = () => {
    resetUploadForm(currentPrefix);
    setUploadDialogOpen(true);
  };

  const resolveUploadPath = (selected: File, pathInput: string): string | undefined => {
    const trimmed = pathInput.trim();
    if (!trimmed) {
      // Stay in current directory when the field is cleared.
      const dir = normalizeDirPrefix(currentPrefix);
      return dir ? `${dir}${selected.name}` : selected.name;
    }
    if (trimmed.endsWith('/')) {
      return `${trimmed}${selected.name}`;
    }
    return trimmed;
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const path = resolveUploadPath(file, uploadPath);
      const response = await floConsoleService.datasourcesService.uploadFile(datasourceId, file, path);
      const returned = response.data?.data?.path;
      if (!returned) {
        notifyError('Upload succeeded but no path was returned');
        return;
      }
      notifySuccess('File uploaded successfully');
      setUploadDialogOpen(false);
      resetUploadForm(currentPrefix);
      await loadFiles(currentPrefix);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to upload file');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (entry: DatasourceFileEntry) => {
    setDownloadingPath(entry.path);
    try {
      const response = await floConsoleService.datasourcesService.downloadFile(datasourceId, entry.relative_path);
      downloadBlobFile(entry.name || 'download', response.data);
    } catch (error) {
      notifyError((await getDownloadErrorMessage(error)) || 'Failed to download file');
    } finally {
      setDownloadingPath(null);
    }
  };

  const handlePreview = async (entry: DatasourceFileEntry) => {
    clearPreview();
    setPreviewLoadingPath(entry.path);
    try {
      const response = await floConsoleService.datasourcesService.downloadFile(datasourceId, entry.relative_path);
      const blob = response.data;
      const contentType = mimeTypeOf(response.headers?.['content-type'], blob.type);
      const kind = previewKindFor(contentType);

      if (kind === 'image' || kind === 'video') {
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setPreview({
          entry,
          kind,
          objectUrl,
          contentType,
          sizeBytes: blob.size,
        });
        return;
      }

      if (kind === 'text') {
        if (blob.size > TEXT_PREVIEW_MAX_BYTES) {
          setPreview({
            entry,
            kind: 'unsupported',
            contentType,
            sizeBytes: blob.size,
          });
          return;
        }
        setPreview({
          entry,
          kind: 'text',
          text: await blob.text(),
          contentType,
          sizeBytes: blob.size,
        });
        return;
      }

      setPreview({
        entry,
        kind: 'unsupported',
        contentType,
        sizeBytes: blob.size,
      });
    } catch (error) {
      notifyError((await getDownloadErrorMessage(error)) || 'Failed to open file');
      clearPreview();
    } finally {
      setPreviewLoadingPath(null);
    }
  };

  const handleCopy = async (value: string) => {
    if (await copyToClipboard(value)) {
      notifySuccess('Copied path to clipboard');
    } else {
      notifyError('Failed to copy path');
    }
  };

  const handleDelete = async () => {
    if (!filePendingDelete) return;
    setDeleting(true);
    try {
      await floConsoleService.datasourcesService.deleteFile(datasourceId, filePendingDelete.relative_path);
      if (preview?.entry.path === filePendingDelete.path) {
        clearPreview();
      }
      notifySuccess('File deleted');
      setFilePendingDelete(null);
      await loadFiles(currentPrefix);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete file');
    } finally {
      setDeleting(false);
    }
  };

  const navigateTo = (prefix: string) => {
    clearPreview();
    setCurrentPrefix(normalizeDirPrefix(prefix));
  };

  const locationLabel = currentPrefix ? currentPrefix.replace(/\/$/, '') : '/';

  return (
    <div className="frost-panel ring-frost-border flex min-h-0 flex-col rounded-xl border ring-1">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EFF0F1] px-6 py-4">
        <div className="min-w-0">
          <h2 className="frost-text text-lg font-semibold">Files</h2>
          <p className="frost-text-muted text-sm">Browse folders under this datasource base path</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadFiles(currentPrefix)}
            disabled={loadingFiles}
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loadingFiles ? 'animate-spin' : ''}`} />
          </Button>
          <Button size="sm" onClick={openUploadDialog}>
            <Upload className="mr-1.5 h-4 w-4" />
            Upload
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-[#EFF0F1] px-6 py-2.5">
        <button
          type="button"
          className={`text-sm ${currentPrefix ? 'text-brand hover:underline' : 'frost-text font-medium'}`}
          onClick={() => navigateTo('')}
          disabled={!currentPrefix}
        >
          Root
        </button>
        {crumbs.map((crumb) => (
          <React.Fragment key={crumb.prefix}>
            <ChevronRight className="frost-text-subtle h-3.5 w-3.5 shrink-0" />
            <button
              type="button"
              className={`max-w-[12rem] truncate text-sm ${
                crumb.prefix === currentPrefix ? 'frost-text font-medium' : 'text-brand hover:underline'
              }`}
              title={crumb.prefix}
              onClick={() => navigateTo(crumb.prefix)}
              disabled={crumb.prefix === currentPrefix}
            >
              {crumb.label}
            </button>
          </React.Fragment>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        {loadingFiles && browserRows.length === 0 ? (
          <p className="frost-text-muted text-sm">Loading files…</p>
        ) : browserRows.length === 0 ? (
          <p className="frost-text-muted text-sm">
            {currentPrefix ? 'This folder is empty.' : 'No files yet. Upload one to get started.'}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Path</TableHead>
                <TableHead className="w-[1%] text-right whitespace-nowrap">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {browserRows.map((row) =>
                row.kind === 'folder' ? (
                  <TableRow key={`folder:${row.prefix}`}>
                    <TableCell className="frost-text font-medium">
                      <button
                        type="button"
                        className="text-brand inline-flex items-center gap-2 text-left hover:underline"
                        onClick={() => navigateTo(row.prefix)}
                      >
                        <Folder className="h-4 w-4 shrink-0" />
                        {row.name}
                      </button>
                    </TableCell>
                    <TableCell>
                      <span className="frost-text truncate font-mono text-sm" title={row.prefix}>
                        {row.prefix.replace(/\/$/, '')}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" title="Open folder" onClick={() => navigateTo(row.prefix)}>
                        Open
                      </Button>
                    </TableCell>
                  </TableRow>
                ) : (
                  <TableRow key={row.entry.path}>
                    <TableCell className="frost-text font-medium">
                      <button
                        type="button"
                        className="text-brand text-left hover:underline disabled:opacity-60"
                        title="Preview file"
                        disabled={previewLoadingPath === row.entry.path}
                        onClick={() => void handlePreview(row.entry)}
                      >
                        {previewLoadingPath === row.entry.path ? 'Opening…' : row.entry.name}
                      </button>
                    </TableCell>
                    <TableCell>
                      <div className="flex min-w-0 items-center gap-1">
                        <span className="frost-text truncate font-mono text-sm" title={row.entry.path}>
                          {row.entry.relative_path}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Copy datasource path"
                          onClick={() => void handleCopy(row.entry.path)}
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Download"
                          loading={downloadingPath === row.entry.path}
                          disabled={downloadingPath === row.entry.path || deleting}
                          onClick={() => void handleDownload(row.entry)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Delete"
                          disabled={deleting}
                          onClick={() => setFilePendingDelete(row.entry)}
                        >
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              )}
            </TableBody>
          </Table>
        )}

        {listTruncated && (
          <p className="frost-text-muted mt-3 text-xs">
            Listing stopped after {MAX_LIST_PAGES * PAGE_SIZE} objects under this path. Some deeper entries may be
            missing.
          </p>
        )}
      </div>

      <Dialog
        open={uploadDialogOpen}
        onOpenChange={(open) => {
          setUploadDialogOpen(open);
          if (!open) resetUploadForm(currentPrefix);
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Upload file</DialogTitle>
            <DialogDescription>
              Uploading into <span className="font-mono text-xs">{locationLabel}</span>. Use a trailing{' '}
              <span className="font-mono">/</span> to keep the original file name, or set a full relative path.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="fileStorageUpload">File</Label>
              <Input
                ref={fileInputRef}
                type="file"
                id="fileStorageUpload"
                onChange={(e) => {
                  const next = e.target.files ? e.target.files[0] : null;
                  setFile(next);
                  // Keep directory destination; append name only when path is a bare folder or empty.
                  if (next) {
                    setUploadPath((prev) => {
                      const trimmed = prev.trim();
                      if (!trimmed || trimmed.endsWith('/')) {
                        return normalizeDirPrefix(trimmed || currentPrefix);
                      }
                      return trimmed;
                    });
                  }
                }}
                disabled={uploading}
                className="frost-control ring-frost-border frost-text file:text-brand w-full cursor-pointer border px-3 py-2 text-sm ring-1 outline-none file:cursor-pointer"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="fileStorageUploadPath">Destination path (relative)</Label>
              <Input
                id="fileStorageUploadPath"
                placeholder="folder/ or folder/name.ext"
                value={uploadPath}
                onChange={(e) => setUploadPath(e.target.value)}
                disabled={uploading}
              />
              <p className="frost-text-subtle text-xs">
                Relative to the datasource base path. Current folder is pre-filled.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadDialogOpen(false)} disabled={uploading}>
              Cancel
            </Button>
            <Button onClick={() => void handleUpload()} loading={uploading} disabled={!file || uploading}>
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={preview !== null || previewLoadingPath !== null}
        onOpenChange={(open) => {
          if (!open) clearPreview();
        }}
      >
        <DialogContent className="flex max-h-[90vh] max-w-3xl min-w-0 flex-col overflow-hidden lg:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-6">
              {preview?.entry.name || files.find((entry) => entry.path === previewLoadingPath)?.name || 'File preview'}
            </DialogTitle>
            <DialogDescription className="truncate font-mono text-xs">
              {preview?.entry.relative_path ||
                files.find((entry) => entry.path === previewLoadingPath)?.relative_path ||
                'Loading…'}
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-auto py-2">
            {previewLoadingPath && !preview ? (
              <p className="frost-text-muted text-sm">Loading preview…</p>
            ) : preview?.kind === 'image' && preview.objectUrl ? (
              <img
                src={preview.objectUrl}
                alt={preview.entry.name}
                className="mx-auto max-h-[60vh] max-w-full rounded-md object-contain"
              />
            ) : preview?.kind === 'video' && preview.objectUrl ? (
              <video src={preview.objectUrl} controls className="mx-auto max-h-[60vh] max-w-full rounded-md" />
            ) : preview?.kind === 'text' ? (
              <pre className="frost-text bg-muted/40 max-h-[60vh] overflow-auto rounded-md p-4 text-xs break-words whitespace-pre-wrap">
                {preview.text}
              </pre>
            ) : preview ? (
              <div className="frost-text-muted flex flex-col gap-2 text-sm">
                <p>Preview is not available for this file type.</p>
                <p className="font-mono text-xs">
                  {preview.contentType || 'application/octet-stream'} · {preview.sizeBytes} bytes
                </p>
              </div>
            ) : null}
          </div>

          {preview && (
            <DialogFooter>
              <Button variant="outline" onClick={clearPreview}>
                Close
              </Button>
              <Button variant="destructive" disabled={deleting} onClick={() => setFilePendingDelete(preview.entry)}>
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                Delete
              </Button>
              <Button onClick={() => void handleDownload(preview.entry)}>
                <Download className="mr-1.5 h-3.5 w-3.5" />
                Download
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        isOpen={filePendingDelete !== null}
        title="Delete file"
        message={
          filePendingDelete
            ? `Delete "${filePendingDelete.name}" (${filePendingDelete.relative_path})? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => {
          if (!deleting) setFilePendingDelete(null);
        }}
      />
    </div>
  );
};

export default FileStoragePanel;
