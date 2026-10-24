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
import { cn, copyToClipboard, downloadBlobFile, extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { DatasourceBrowseFileEntry, DatasourceFileEntry, DatasourceFolderEntry } from '@app/types/datasource';
import dayjs from 'dayjs';
import {
  Check,
  ChevronRight,
  Copy,
  Download,
  Eye,
  File,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  FolderPlus,
  FolderUp,
  HardDrive,
  Loader2,
  X,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PickedFile, pickedFromDrop, pickedFromInput, toBatches } from './dropped-files';

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

/** One folder's contents as loaded so far from `files/browse`. */
interface FolderState {
  folders: DatasourceFolderEntry[];
  files: DatasourceBrowseFileEntry[];
  /** Token for the next page; null once everything is loaded. */
  nextPageToken: string | null;
  loading: boolean;
  loaded: boolean;
  error?: string;
}

/** A file picked for upload and how far it has got. */
interface QueuedUpload extends PickedFile {
  status: 'pending' | 'uploading' | 'done' | 'failed';
  error?: string;
}

const TEXT_PREVIEW_MAX_BYTES = 512 * 1024;
// Rows the upload list renders; a dropped folder can hold thousands of files.
const QUEUE_ROWS_SHOWN = 300;
const PAGE_SIZE = 200;

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

const breadcrumbSegments = (dirPrefix: string): { label: string; prefix: string }[] => {
  const trimmed = dirPrefix.replace(/^\/+|\/+$/g, '');
  if (!trimmed) return [];
  const parts = trimmed.split('/');
  return parts.map((label, index) => ({
    label,
    prefix: `${parts.slice(0, index + 1).join('/')}/`,
  }));
};

/** Every ancestor folder of a prefix, root first: 'a/b/' -> ['', 'a/', 'a/b/']. */
const ancestorPrefixes = (dirPrefix: string): string[] => [
  '',
  ...breadcrumbSegments(dirPrefix).map((segment) => segment.prefix),
];

/** The folder a file path lives in: 'a/b/c.txt' -> 'a/b/'. */
const parentPrefix = (path: string) => {
  const slash = path.replace(/^\/+/, '').lastIndexOf('/');
  return slash === -1 ? '' : path.replace(/^\/+/, '').slice(0, slash + 1);
};

/** An icon that hints at what a file is, from its extension. */
const fileIconFor = (name: string) => {
  const extension = name.split('.').pop()?.toLowerCase() ?? '';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(extension)) return FileImage;
  if (['mp4', 'mov', 'webm', 'mkv', 'avi'].includes(extension)) return FileVideo;
  if (['csv', 'xls', 'xlsx', 'parquet', 'tsv'].includes(extension)) return FileSpreadsheet;
  if (['json', 'yaml', 'yml', 'xml', 'js', 'ts', 'py', 'sql', 'html'].includes(extension)) return FileCode;
  if (['txt', 'md', 'log', 'pdf', 'doc', 'docx'].includes(extension)) return FileText;
  return File;
};

const fileTypeLabel = (name: string) => {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : 'File';
};

const formatBytes = (bytes: number | null) => {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
};

/** One folder in the left-hand tree; its sub-folders load the first time it is expanded. */
const TreeFolder = ({
  folder,
  depth,
  selected,
  expanded,
  cache,
  onSelect,
  onToggle,
}: {
  folder: DatasourceFolderEntry;
  depth: number;
  selected: string;
  expanded: Set<string>;
  cache: Record<string, FolderState>;
  onSelect: (prefix: string) => void;
  onToggle: (prefix: string) => void;
}) => {
  const state = cache[folder.prefix];
  const open = expanded.has(folder.prefix);
  // Until it's loaded we can't know, so offer the chevron; once loaded, only if it has sub-folders.
  const mayHaveChildren = !state?.loaded || state.folders.length > 0;
  const isSelected = selected === folder.prefix;
  const FolderIcon = open && state?.folders.length ? FolderOpen : Folder;
  return (
    <li>
      <div
        className={cn(
          'flex items-center gap-1 rounded-md py-1 pr-2 text-sm transition-colors',
          isSelected ? 'bg-brand/12 text-brand font-medium' : 'frost-text hover:bg-frost-glass'
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        <button
          type="button"
          aria-label={open ? `Collapse ${folder.name}` : `Expand ${folder.name}`}
          aria-expanded={mayHaveChildren ? open : undefined}
          onClick={() => onToggle(folder.prefix)}
          className={cn(
            'frost-text-subtle hover:text-frost-text flex size-5 shrink-0 items-center justify-center rounded',
            mayHaveChildren ? 'cursor-pointer' : 'invisible'
          )}
        >
          {open && state?.loading && !state.loaded ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
          )}
        </button>
        <button
          type="button"
          onClick={() => onSelect(folder.prefix)}
          title={folder.prefix}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
        >
          <FolderIcon className={cn('size-4 shrink-0', isSelected ? 'text-brand' : 'text-amber-500')} />
          <span className="truncate">{folder.name}</span>
        </button>
      </div>
      {open && state?.folders.length ? (
        <ul>
          {state.folders.map((child) => (
            <TreeFolder
              key={child.prefix}
              folder={child}
              depth={depth + 1}
              selected={selected}
              expanded={expanded}
              cache={cache}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
};

/**
 * A storage browser like a cloud console's: the folder tree on the left, the open folder's contents on the right,
 * with upload, preview, download and delete. Each folder is fetched one level at a time from `files/browse` the
 * first time it is opened or expanded, then kept until a refresh.
 */
const FileStoragePanel: React.FC<FileStoragePanelProps> = ({ datasourceId }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
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

  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [uploadQueue, setUploadQueue] = useState<QueuedUpload[]>([]);
  const [uploading, setUploading] = useState(false);
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

  /** Adds files to the upload list, replacing any still-pending one with the same path. */
  const queueFiles = (picked: PickedFile[]) => {
    if (picked.length === 0) return;
    const paths = new Set(picked.map((item) => item.relativePath));
    setUploadQueue((queue) => [
      ...queue.filter((item) => item.status !== 'pending' || !paths.has(item.relativePath)),
      ...picked.map((item) => ({ ...item, status: 'pending' as const })),
    ]);
  };

  const openUploadDialog = (picked?: PickedFile[]) => {
    setUploadQueue([]);
    if (picked) queueFiles(picked);
    setUploadDialogOpen(true);
  };

  /** Files (and folders) dropped from the desktop, opened up into a flat list with their paths. */
  const dropFiles = async (dataTransfer: DataTransfer, intoDialog: boolean) => {
    try {
      const picked = await pickedFromDrop(dataTransfer);
      if (intoDialog) queueFiles(picked);
      else openUploadDialog(picked);
    } catch {
      notifyError('Could not read the dropped files');
    }
  };

  /**
   * Uploads everything not yet done into the open folder, keeping each file's sub-folder path. Files go in
   * batches (50 files or 25 MB per request); each file is marked done or failed from its batch's results.
   */
  const handleUpload = async () => {
    const target = currentPrefix;
    const todo = uploadQueue.map((item, index) => ({ ...item, index })).filter((item) => item.status !== 'done');
    const setStatus = (indexes: number[], patch: (index: number) => Partial<QueuedUpload>) => {
      const wanted = new Set(indexes);
      setUploadQueue((queue) => queue.map((entry, i) => (wanted.has(i) ? { ...entry, ...patch(i) } : entry)));
    };

    setUploading(true);
    let uploaded = 0;
    let failed = 0;
    for (const batch of toBatches(todo)) {
      const indexes = batch.map((item) => item.index);
      setStatus(indexes, () => ({ status: 'uploading', error: undefined }));
      try {
        const response = await floConsoleService.datasourcesService.uploadFilesBatch(
          datasourceId,
          batch.map((item) => ({ file: item.file, path: `${target}${item.relativePath}` }))
        );
        const results = response.data?.data?.results ?? [];
        const errors = new Map(results.filter((r) => r.error).map((r) => [indexes[r.index], r.error!]));
        setStatus(indexes, (index) =>
          errors.has(index) ? { status: 'failed', error: errors.get(index) } : { status: 'done' }
        );
        failed += errors.size;
        uploaded += batch.length - errors.size;
      } catch (error) {
        const message = extractErrorMessage(error) || 'Upload failed';
        setStatus(indexes, () => ({ status: 'failed', error: message }));
        failed += batch.length;
      }
    }
    setUploading(false);

    if (uploaded > 0) {
      notifySuccess(`Uploaded ${uploaded} file${uploaded === 1 ? '' : 's'}`);
      // The open folder, plus any expanded folder under it, since a folder upload can add files to those too.
      reloadFolders([target, ...[...expanded].filter((prefix) => prefix.startsWith(target) && prefix !== target)]);
    }
    if (failed > 0) notifyError(`${failed} file${failed === 1 ? '' : 's'} failed to upload`);
    // Close when everything went up; stay open to show what failed otherwise.
    else setUploadDialogOpen(false);
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

  const locationLabel = currentPrefix ? currentPrefix.replace(/\/$/, '') : '/';
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
          className={cn('relative min-h-0 flex-1 overflow-auto', dragging && !uploadDialogOpen && 'bg-brand/5')}
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
            void dropFiles(e.dataTransfer, false);
          }}
        >
          {dragging && !uploadDialogOpen ? (
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

      <Dialog open={uploadDialogOpen} onOpenChange={(open) => !uploading && setUploadDialogOpen(open)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Upload files</DialogTitle>
            <DialogDescription className="flex items-center gap-1.5">
              Into
              <span className="frost-text inline-flex min-w-0 items-center gap-1 font-medium">
                {currentPrefix ? (
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
              void dropFiles(e.dataTransfer, true);
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
                <button
                  type="button"
                  onClick={() => setUploadQueue((queue) => queue.filter((item) => item.status === 'done'))}
                  className="hover:text-frost-text cursor-pointer"
                >
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
                const replaces =
                  !item.relativePath.includes('/') &&
                  (current?.files ?? []).some((entry) => entry.name === item.file.name);
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
                        onClick={() => setUploadQueue((queue) => queue.filter((_, i) => i !== index))}
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
            <Button variant="outline" onClick={() => setUploadDialogOpen(false)} disabled={uploading}>
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
        <DialogContent className="flex max-h-[90vh] max-w-3xl min-w-0 flex-col overflow-hidden lg:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-6">
              {preview?.entry.name ||
                current?.files.find((entry) => entry.path === previewLoadingPath)?.name ||
                'File preview'}
            </DialogTitle>
            <DialogDescription className="truncate font-mono text-xs">
              {preview?.entry.relative_path ||
                current?.files.find((entry) => entry.path === previewLoadingPath)?.relative_path ||
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
                  {preview.contentType || 'application/octet-stream'} · {formatBytes(preview.sizeBytes)}
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
