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
import { Skeleton } from '@app/components/ui/skeleton';
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { cn } from '@app/lib/utils';
import { copyToClipboard } from '@app/utils/clipboard';
import { downloadBlobFile } from '@app/utils/download';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { DatasourceFileEntry } from '@app/types/datasource';
import dayjs from 'dayjs';
import {
  ChevronRight,
  Copy,
  Download,
  Eye,
  Folder,
  FolderOpen,
  FolderPlus,
  HardDrive,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PickedFile, pickedFromDrop } from './dropped-files';
import {
  FilePreviewState,
  FolderState,
  TEXT_PREVIEW_MAX_BYTES,
  PAGE_SIZE,
  getDownloadErrorMessage,
  mimeTypeOf,
  previewKindFor,
  normalizeDirPrefix,
  breadcrumbSegments,
  ancestorPrefixes,
  parentPrefix,
  fileIconFor,
  fileTypeLabel,
  formatBytes,
  locationLabelFor,
} from './file-storage';
import { TreeFolder } from './FileStorageTree';
import FileUploadDialog from './FileUploadDialog';

interface FileStoragePanelProps {
  datasourceId: string;
}

const FileStoragePanel: React.FC<FileStoragePanelProps> = ({ datasourceId }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const previewObjectUrlRef = useRef<string | null>(null);
  const previewRequestIdRef = useRef(0);

  /** Current directory: '' root, or 'docs/reports/' */
  const [currentPrefix, setCurrentPrefix] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['']));
  const [nameFilter, setNameFilter] = useState('');
  const [cache, setCache] = useState<Record<string, FolderState>>({});
  // Lets async loads see the latest cache without re-creating every callback that reads it.
  const cacheRef = useRef(cache);
  cacheRef.current = cache;
  // Bumped on refresh, so a load that started before it can't write stale results back.
  const generationRef = useRef(0);

  const [uploadDialog, setUploadDialog] = useState<{ open: boolean; files: PickedFile[] }>({ open: false, files: [] });
  const [dragging, setDragging] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);

  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);
  const [filePendingDelete, setFilePendingDelete] = useState<DatasourceFileEntry | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [preview, setPreview] = useState<FilePreviewState | null>(null);
  const [previewLoadingPath, setPreviewLoadingPath] = useState<string | null>(null);

  /** Loads a folder's first page, or with `more` its next one. Already-loaded folders are left alone. */
  const loadFolder = useCallback(
    async (prefix: string, { more = false, force = false }: { more?: boolean; force?: boolean } = {}) => {
      const existing = cacheRef.current[prefix];
      if (existing?.loading) return;
      if (!more && !force && existing?.loaded) return;
      if (more && !existing?.nextPageToken) return;

      const generation = generationRef.current;
      setCache((current) => ({
        ...current,
        [prefix]: {
          folders: more ? (current[prefix]?.folders ?? []) : [],
          files: more ? (current[prefix]?.files ?? []) : [],
          nextPageToken: more ? (current[prefix]?.nextPageToken ?? null) : null,
          loaded: more ? Boolean(current[prefix]?.loaded) : false,
          loading: true,
        },
      }));
      try {
        const response = await floConsoleService.datasourcesService.browseFiles(datasourceId, {
          prefix: prefix || undefined,
          page_size: PAGE_SIZE,
          page_token: more ? (existing?.nextPageToken ?? undefined) : undefined,
        });
        if (generation !== generationRef.current) return;
        const data = response.data?.data;
        setCache((current) => {
          const previous = more ? current[prefix] : undefined;
          return {
            ...current,
            [prefix]: {
              folders: [...(previous?.folders ?? []), ...(data?.folders ?? [])],
              files: [...(previous?.files ?? []), ...(data?.files ?? [])],
              nextPageToken: data?.next_page_token ?? null,
              loading: false,
              loaded: true,
            },
          };
        });
      } catch (error) {
        if (generation !== generationRef.current) return;
        const message = extractErrorMessage(error) || 'Failed to list files';
        setCache((current) => ({
          ...current,
          [prefix]: {
            ...(current[prefix] ?? { folders: [], files: [], nextPageToken: null }),
            loading: false,
            loaded: true,
            error: message,
          },
        }));
        notifyError(message);
      }
    },
    [datasourceId, notifyError]
  );

  // The root, then whatever folder is open (its ancestors too, so the tree can show the way down to it).
  useEffect(() => {
    ancestorPrefixes(currentPrefix).forEach((prefix) => void loadFolder(prefix));
  }, [currentPrefix, loadFolder]);

  /** Drops everything loaded and fetches again what's on screen: the open folder and every expanded one. */
  const refresh = useCallback(() => {
    generationRef.current += 1;
    cacheRef.current = {};
    setCache({});
    const visible = new Set([...ancestorPrefixes(currentPrefix), ...expanded]);
    visible.forEach((prefix) => void loadFolder(prefix, { force: true }));
  }, [currentPrefix, expanded, loadFolder]);

  /** Re-fetches only the folders a change touched, keeping the rest of the tree as it is. */
  const reloadFolders = (prefixes: string[]) =>
    new Set(prefixes).forEach((prefix) => void loadFolder(prefix, { force: true }));

  const current = cache[currentPrefix];
  const query = nameFilter.trim().toLowerCase();
  const visibleFolders = useMemo(
    () => (current?.folders ?? []).filter((folder) => folder.name.toLowerCase().includes(query)),
    [current, query]
  );
  const visibleFiles = useMemo(
    () => (current?.files ?? []).filter((entry) => entry.name.toLowerCase().includes(query)),
    [current, query]
  );
  const crumbs = useMemo(() => breadcrumbSegments(currentPrefix), [currentPrefix]);
  const firstLoad = !current?.loaded;
  const rootState = cache[''];

  const clearPreview = useCallback(() => {
    // Invalidate any in-flight preview request
    previewRequestIdRef.current += 1;
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setPreview(null);
    setPreviewLoadingPath(null);
  }, []);

  useEffect(() => () => clearPreview(), [clearPreview]);

  const openUploadDialog = (picked?: PickedFile[]) => setUploadDialog({ open: true, files: picked ?? [] });

  /** Files (and folders) dropped on the list open the upload dialog with them queued. */
  const dropFiles = async (dataTransfer: DataTransfer) => {
    try {
      openUploadDialog(await pickedFromDrop(dataTransfer));
    } catch {
      notifyError('Could not read the dropped files');
    }
  };

  const folderNameProblem = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return 'Enter a name';
    if (trimmed.includes('/') || trimmed.includes('\\')) return 'A folder name cannot contain slashes';
    if (trimmed === '.' || trimmed === '..') return 'Pick another name';
    if ((current?.folders ?? []).some((folder) => folder.name === trimmed))
      return 'A folder with this name exists here';
    return null;
  };

  const handleCreateFolder = async () => {
    const name = newFolderName.trim();
    if (folderNameProblem(name)) return;
    setCreatingFolder(true);
    try {
      await floConsoleService.datasourcesService.createFolder(datasourceId, `${currentPrefix}${name}`);
      notifySuccess(`Created folder ${name}`);
      setNewFolderOpen(false);
      setNewFolderName('');
      reloadFolders([currentPrefix]);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to create the folder');
    } finally {
      setCreatingFolder(false);
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
    const requestId = previewRequestIdRef.current;
    const isStale = () => previewRequestIdRef.current !== requestId;
    setPreviewLoadingPath(entry.path);
    try {
      const response = await floConsoleService.datasourcesService.downloadFile(datasourceId, entry.relative_path);
      if (isStale()) return;
      const blob = response.data;
      const headerContentType = response.headers?.['content-type'];
      const contentType = mimeTypeOf(typeof headerContentType === 'string' ? headerContentType : undefined, blob.type);
      const kind = previewKindFor(contentType);

      if (kind === 'image' || kind === 'video') {
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setPreview({ entry, kind, objectUrl, contentType, sizeBytes: blob.size });
        return;
      }

      if (kind === 'text') {
        if (blob.size > TEXT_PREVIEW_MAX_BYTES) {
          setPreview({ entry, kind: 'unsupported', contentType, sizeBytes: blob.size });
          return;
        }
        const text = await blob.text();
        if (isStale()) return;
        setPreview({ entry, kind: 'text', text, contentType, sizeBytes: blob.size });
        return;
      }

      setPreview({ entry, kind: 'unsupported', contentType, sizeBytes: blob.size });
    } catch (error) {
      if (isStale()) return;
      const message = await getDownloadErrorMessage(error);
      if (isStale()) return;
      notifyError(message || 'Failed to open file');
      clearPreview();
    } finally {
      if (!isStale()) setPreviewLoadingPath(null);
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
      const folder = parentPrefix(filePendingDelete.relative_path);
      setFilePendingDelete(null);
      // Its folder, and the one above in case that was its last file and the folder is gone.
      reloadFolders([folder, ...ancestorPrefixes(folder).slice(-2)]);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete file');
    } finally {
      setDeleting(false);
    }
  };

  /** Opens a folder on the right and unfolds the tree down to it. */
  const navigateTo = (prefix: string) => {
    const next = normalizeDirPrefix(prefix);
    clearPreview();
    setNameFilter('');
    setCurrentPrefix(next);
    setExpanded((open) => new Set([...open, ...ancestorPrefixes(next)]));
  };

  const toggleFolder = (prefix: string) => {
    const opening = !expanded.has(prefix);
    setExpanded((open) => {
      const next = new Set(open);
      if (next.has(prefix)) next.delete(prefix);
      else next.add(prefix);
      return next;
    });
    if (opening) void loadFolder(prefix);
  };

  const locationLabel = locationLabelFor(currentPrefix);
  // The file being previewed, known from the click even before its bytes arrive.
  const previewEntry = preview?.entry ?? current?.files.find((entry) => entry.path === previewLoadingPath) ?? null;
  const loadingAny = Object.values(cache).some((state) => state.loading);

  return (
    <div className="grid min-h-0 flex-1 gap-6 overflow-hidden lg:grid-cols-[280px_1fr]">
      {/* Folders */}
      <div className="frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1 max-lg:max-h-72">
        <div className="border-frost-border flex shrink-0 items-center justify-between gap-2 border-b px-4 py-3">
          <h2 className="frost-text text-sm font-semibold">Folders</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(new Set(['']))}
            disabled={expanded.size <= 1}
            className="h-7 px-2 text-xs"
          >
            Collapse all
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          <ul>
            <li>
              <button
                type="button"
                onClick={() => navigateTo('')}
                className={cn(
                  'flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                  currentPrefix === '' ? 'bg-brand/12 text-brand font-medium' : 'frost-text hover:bg-frost-glass'
                )}
              >
                <HardDrive className="size-4 shrink-0" />
                <span className="truncate">Root</span>
              </button>
              {!rootState?.loaded ? (
                Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="my-2 mr-2 ml-7 h-4" />)
              ) : rootState.folders.length > 0 ? (
                <ul>
                  {rootState.folders.map((folder) => (
                    <TreeFolder
                      key={folder.prefix}
                      folder={folder}
                      depth={1}
                      selected={currentPrefix}
                      expanded={expanded}
                      cache={cache}
                      onSelect={navigateTo}
                      onToggle={toggleFolder}
                    />
                  ))}
                </ul>
              ) : null}
            </li>
          </ul>
        </div>
      </div>

      {/* Contents of the open folder */}
      <div className="frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1">
        <div className="border-frost-border flex shrink-0 flex-wrap items-center gap-2 border-b px-4 py-3">
          <nav aria-label="Folder path" className="mr-auto flex min-w-0 flex-wrap items-center gap-1 text-sm">
            <button
              type="button"
              className={cn(
                'cursor-pointer',
                currentPrefix ? 'text-brand hover:underline' : 'frost-text font-semibold'
              )}
              onClick={() => navigateTo('')}
              disabled={!currentPrefix}
            >
              Root
            </button>
            {crumbs.map((crumb) => (
              <React.Fragment key={crumb.prefix}>
                <ChevronRight className="frost-text-subtle size-3.5 shrink-0" />
                <button
                  type="button"
                  className={cn(
                    'max-w-48 cursor-pointer truncate',
                    crumb.prefix === currentPrefix ? 'frost-text font-semibold' : 'text-brand hover:underline'
                  )}
                  title={crumb.prefix}
                  onClick={() => navigateTo(crumb.prefix)}
                  disabled={crumb.prefix === currentPrefix}
                >
                  {crumb.label}
                </button>
              </React.Fragment>
            ))}
          </nav>
          <div className="relative">
            <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
              placeholder="Filter by name"
              aria-label="Filter this folder by name"
              className="h-9 w-48 pl-9"
            />
          </div>
          <Button variant="outline" size="sm" onClick={refresh} disabled={loadingAny} title="Refresh">
            <RefreshCw className={cn('size-4', loadingAny && 'animate-spin')} />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setNewFolderOpen(true)}>
            <FolderPlus className="size-4" />
            New folder
          </Button>
          <Button size="sm" onClick={() => openUploadDialog()}>
            <Upload className="size-4" />
            Upload
          </Button>
        </div>

        {/* Files dropped anywhere on the list go to the upload dialog, headed for the open folder. */}
        <div
          className={cn('relative min-h-0 flex-1 overflow-auto', dragging && !uploadDialog.open && 'bg-brand/5')}
          onDragOver={(e) => {
            if (!e.dataTransfer.types.includes('Files')) return;
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
          }}
          onDrop={(e) => {
            if (!e.dataTransfer.types.includes('Files')) return;
            e.preventDefault();
            setDragging(false);
            void dropFiles(e.dataTransfer);
          }}
        >
          {dragging && !uploadDialog.open ? (
            <div className="border-brand text-brand pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed text-sm font-medium">
              Drop to upload into {locationLabel}
            </div>
          ) : null}
          {firstLoad ? (
            <div className="flex flex-col gap-3 p-4">
              {Array.from({ length: 8 }).map((_, index) => (
                <Skeleton key={index} className="h-5" />
              ))}
            </div>
          ) : current?.error && visibleFolders.length === 0 && visibleFiles.length === 0 ? (
            <p className="px-6 py-16 text-center text-sm text-red-500">{current.error}</p>
          ) : visibleFolders.length === 0 && visibleFiles.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
              <span className="bg-brand/12 text-brand flex size-12 items-center justify-center rounded-2xl">
                <FolderOpen className="size-5" />
              </span>
              <p className="frost-text text-sm font-medium">
                {nameFilter
                  ? 'Nothing here matches that name'
                  : currentPrefix
                    ? 'This folder is empty'
                    : 'No files yet'}
              </p>
              {!nameFilter ? (
                <Button size="sm" variant="outline" onClick={() => openUploadDialog()}>
                  <Upload className="size-4" />
                  Upload a file here
                </Button>
              ) : null}
            </div>
          ) : (
            <table className="w-full caption-bottom text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Name</TableHead>
                  <TableHead className="w-24 text-right">Size</TableHead>
                  <TableHead className="w-24 max-sm:hidden">Type</TableHead>
                  <TableHead className="w-44 max-md:hidden">Last modified</TableHead>
                  <TableHead className="w-px pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleFolders.map((folder) => (
                  <TableRow
                    key={`folder:${folder.prefix}`}
                    className="cursor-pointer"
                    onClick={() => navigateTo(folder.prefix)}
                  >
                    <TableCell className="pl-4">
                      <span className="frost-text inline-flex min-w-0 items-center gap-2 font-medium">
                        <Folder className="size-4 shrink-0 text-amber-500" />
                        <span className="truncate">{folder.name}</span>
                      </span>
                    </TableCell>
                    <TableCell className="frost-text-subtle text-right text-xs">—</TableCell>
                    <TableCell className="frost-text-muted text-xs max-sm:hidden">Folder</TableCell>
                    <TableCell className="frost-text-subtle text-xs max-md:hidden">—</TableCell>
                    <TableCell className="pr-4" />
                  </TableRow>
                ))}
                {visibleFiles.map((entry) => {
                  const Icon = fileIconFor(entry.name);
                  const opening = previewLoadingPath === entry.path;
                  return (
                    <TableRow
                      key={entry.path}
                      className="group cursor-pointer"
                      onClick={() => void handlePreview(entry)}
                    >
                      <TableCell className="max-w-0 pl-4">
                        <span className="frost-text flex min-w-0 items-center gap-2">
                          <Icon className="frost-text-muted size-4 shrink-0" />
                          <span className="truncate" title={entry.relative_path}>
                            {opening ? 'Opening…' : entry.name}
                          </span>
                          <button
                            type="button"
                            title="Copy datasource path"
                            aria-label="Copy datasource path"
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleCopy(entry.path);
                            }}
                            className="frost-text-subtle hover:text-frost-text shrink-0 cursor-pointer opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                          >
                            <Copy className="size-3.5" />
                          </button>
                        </span>
                      </TableCell>
                      <TableCell className="frost-text-muted text-right text-xs whitespace-nowrap tabular-nums">
                        {formatBytes(entry.size)}
                      </TableCell>
                      <TableCell className="frost-text-muted text-xs max-sm:hidden" title={entry.content_type ?? ''}>
                        {fileTypeLabel(entry.name)}
                      </TableCell>
                      <TableCell
                        className="frost-text-muted text-xs whitespace-nowrap max-md:hidden"
                        title={entry.updated_at ?? ''}
                      >
                        {entry.updated_at ? dayjs(entry.updated_at).format('DD MMM YYYY, HH:mm') : '—'}
                      </TableCell>
                      <TableCell className="pr-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-0.5">
                          <Button variant="ghost" size="sm" title="Preview" onClick={() => void handlePreview(entry)}>
                            <Eye className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Download"
                            loading={downloadingPath === entry.path}
                            disabled={downloadingPath === entry.path || deleting}
                            onClick={() => void handleDownload(entry)}
                          >
                            <Download className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Delete"
                            disabled={deleting}
                            onClick={() => setFilePendingDelete(entry)}
                          >
                            <Trash2 className="size-4 text-red-600" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </table>
          )}
        </div>

        {!firstLoad && (visibleFolders.length > 0 || visibleFiles.length > 0 || current?.nextPageToken) ? (
          <div className="border-frost-border frost-text-muted flex shrink-0 items-center justify-between gap-3 border-t px-4 py-2.5 text-xs">
            <span>
              {[
                visibleFolders.length > 0
                  ? `${visibleFolders.length} folder${visibleFolders.length === 1 ? '' : 's'}`
                  : null,
                visibleFiles.length > 0 ? `${visibleFiles.length} file${visibleFiles.length === 1 ? '' : 's'}` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
              {current?.nextPageToken ? ' loaded, more in this folder' : ''}
            </span>
            {current?.nextPageToken ? (
              <Button
                variant="outline"
                size="sm"
                disabled={current.loading}
                onClick={() => void loadFolder(currentPrefix, { more: true })}
              >
                {current.loading ? 'Loading…' : 'Load more'}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      <FileUploadDialog
        open={uploadDialog.open}
        onOpenChange={(open) => setUploadDialog((current) => ({ ...current, open }))}
        datasourceId={datasourceId}
        targetPrefix={currentPrefix}
        initialFiles={uploadDialog.files}
        existingFileNames={(current?.files ?? []).map((entry) => entry.name)}
        onUploaded={(target) =>
          // The folder, plus any expanded folder under it, since a folder upload can add files to those too.
          reloadFolders([target, ...[...expanded].filter((prefix) => prefix.startsWith(target) && prefix !== target)])
        }
      />

      <Dialog
        open={newFolderOpen}
        onOpenChange={(open) => {
          if (creatingFolder) return;
          setNewFolderOpen(open);
          if (!open) setNewFolderName('');
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New folder</DialogTitle>
            <DialogDescription>
              Inside <span className="frost-text font-mono text-xs">{locationLabel}</span>
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleCreateFolder();
            }}
            className="flex flex-col gap-2"
          >
            <Label htmlFor="newFolderName">Name</Label>
            <Input
              id="newFolderName"
              autoFocus
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="e.g. reports"
              disabled={creatingFolder}
            />
            <p
              className={cn(
                'text-xs',
                newFolderName && folderNameProblem(newFolderName) ? 'text-red-500' : 'frost-text-subtle'
              )}
            >
              {(newFolderName && folderNameProblem(newFolderName)) ||
                'It starts empty and appears in the tree right away.'}
            </p>
            <DialogFooter className="mt-2">
              <Button type="button" variant="outline" onClick={() => setNewFolderOpen(false)} disabled={creatingFolder}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={creatingFolder}
                disabled={creatingFolder || Boolean(folderNameProblem(newFolderName))}
              >
                Create folder
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={preview !== null || previewLoadingPath !== null}
        onOpenChange={(open) => {
          if (!open) clearPreview();
        }}
      >
        {/* A fixed size, so the dialog doesn't jump from a spinner to a big image or a page of text. */}
        <DialogContent className="flex h-[80dvh] max-h-[80dvh] max-w-3xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-6">{previewEntry?.name || 'File preview'}</DialogTitle>
            <DialogDescription className="truncate font-mono text-xs">
              {previewEntry?.relative_path}
              {preview ? (
                <span className="frost-text-subtle ml-2 font-sans">
                  {preview.contentType} · {formatBytes(preview.sizeBytes)}
                </span>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          <div className="bg-muted/30 border-frost-border flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg border">
            {previewLoadingPath && !preview ? (
              <div className="frost-text-muted flex flex-col items-center gap-3 text-sm">
                <Loader2 className="text-brand size-7 animate-spin" />
                Loading preview…
              </div>
            ) : preview?.kind === 'image' && preview.objectUrl ? (
              <img src={preview.objectUrl} alt={preview.entry.name} className="max-h-full max-w-full object-contain" />
            ) : preview?.kind === 'video' && preview.objectUrl ? (
              <video src={preview.objectUrl} controls className="max-h-full max-w-full" />
            ) : preview?.kind === 'text' ? (
              <pre className="frost-text h-full w-full overflow-auto p-4 text-xs break-words whitespace-pre-wrap">
                {preview.text}
              </pre>
            ) : preview ? (
              <div className="frost-text-muted flex flex-col items-center gap-3 px-6 text-center text-sm">
                <span className="bg-brand/12 text-brand flex size-12 items-center justify-center rounded-2xl">
                  {React.createElement(fileIconFor(preview.entry.name), { className: 'size-5' })}
                </span>
                <p>
                  {preview.sizeBytes > TEXT_PREVIEW_MAX_BYTES && previewKindFor(preview.contentType) === 'text'
                    ? 'This file is too large to preview here.'
                    : 'Preview is not available for this file type.'}
                </p>
                <p className="text-xs">Download it to open it on your computer.</p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={clearPreview}>
              Close
            </Button>
            <Button
              variant="destructive"
              disabled={deleting || !preview}
              onClick={() => preview && setFilePendingDelete(preview.entry)}
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete
            </Button>
            <Button
              disabled={!previewEntry || downloadingPath === previewEntry.path}
              loading={Boolean(previewEntry && downloadingPath === previewEntry.path)}
              onClick={() => previewEntry && void handleDownload(previewEntry)}
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Download
            </Button>
          </DialogFooter>
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
