import BulkDownloadDialog from '@app/components/BulkDownloadDialog';
import BulkUploadDialog, { MAX_BULK_UPLOAD_FILES } from '@app/components/BulkUploadDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ErrorBanner } from '@app/components/Banner';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { copyToClipboard } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { DynamicQuery } from '@app/types/datasource';
import { Copy, Download, Pencil, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { getDynamicQueryIdFromFileName, parseUploadedDynamicQuery } from './dynamic-query-utils';

type QueryCrudAction = 'view' | 'edit' | 'create' | 'delete' | 'execute';

const DynamicQueries = ({
  dynamicQueries,
  isLoading = false,
  onCreate,
  onDownload,
  onDownloadMany,
  onUploadMany,
  setQueryCrud,
  setSelectedQuery,
}: {
  dynamicQueries: DynamicQuery[];
  isLoading?: boolean;
  onCreate: () => void;
  onDownload: (query: DynamicQuery) => Promise<void>;
  onDownloadMany: (queries: DynamicQuery[]) => Promise<string>;
  onUploadMany: (files: { name: string; id: string; content: string }[]) => Promise<string>;
  setQueryCrud: React.Dispatch<
    React.SetStateAction<{ view: boolean; edit: boolean; create: boolean; delete: boolean; execute: boolean }>
  >;
  setSelectedQuery: React.Dispatch<React.SetStateAction<string | null>>;
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [downloadingFile, setDownloadingFile] = useState<string | null>(null);
  const [bulkDownloadOpen, setBulkDownloadOpen] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [bulkError, setBulkError] = useState('');
  const { notifySuccess, notifyError } = useNotifyStore();

  const filteredQueries = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return dynamicQueries;
    return dynamicQueries.filter((query) => {
      const id = getDynamicQueryIdFromFileName(query.file).toLowerCase();
      return query.version.toLowerCase().includes(term) || query.file.toLowerCase().includes(term) || id.includes(term);
    });
  }, [dynamicQueries, searchTerm]);

  const setOnly = (key: QueryCrudAction, filePath: string) => {
    setQueryCrud({
      view: false,
      edit: false,
      create: false,
      delete: false,
      execute: false,
      [key]: true,
    });
    setSelectedQuery(filePath);
  };

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const handleDownload = async (query: DynamicQuery) => {
    setDownloadingFile(query.file);
    try {
      await onDownload(query);
    } finally {
      setDownloadingFile(null);
    }
  };

  return (
    <div>
      <div className="mb-8 flex w-full items-center justify-end gap-3">
        <Input
          className="w-[200px]"
          type="text"
          placeholder="Search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        <Button variant="outline" onClick={() => setBulkDownloadOpen(true)} disabled={dynamicQueries.length === 0}>
          Download
        </Button>
        <Button variant="outline" onClick={() => setBulkUploadOpen(true)}>
          Upload
        </Button>
        <Button onClick={onCreate}>Create Dynamic Query</Button>
      </div>

      {bulkError ? <ErrorBanner message={bulkError} onDismiss={() => setBulkError('')} /> : null}

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading dynamic queries...</p>
      ) : filteredQueries.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No dynamic queries"
            description="Create a dynamic query to run YAML-defined queries against this datasource"
            actionText="Create Dynamic Query"
            onActionClick={onCreate}
          />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#EFF0F1]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>File</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredQueries.map((query) => {
                const queryId = getDynamicQueryIdFromFileName(query.file);
                return (
                  <TableRow
                    key={query.full_path}
                    className="cursor-pointer"
                    onClick={() => setOnly('view', query.file)}
                  >
                    <TableCell className="whitespace-nowrap">{query.version}</TableCell>
                    <TableCell className="max-w-[240px]" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <span className="truncate font-mono text-xs" title={queryId}>
                          {queryId}
                        </span>
                        <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(queryId)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[360px] truncate" title={query.file}>
                      {query.file}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setOnly('execute', query.file)}>
                          Execute
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Download"
                          loading={downloadingFile === query.file}
                          onClick={() => void handleDownload(query)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" title="Edit" onClick={() => setOnly('edit', query.file)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" title="Delete" onClick={() => setOnly('delete', query.file)}>
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <BulkDownloadDialog
        isOpen={bulkDownloadOpen}
        onOpenChange={setBulkDownloadOpen}
        title="Download Dynamic Queries"
        description="Select the YAML files you want to download."
        emptyLabel="No dynamic queries available"
        items={dynamicQueries}
        getItemId={(query) => query.full_path}
        getItemLabel={(query) => query.file}
        onDownload={async (queries) => {
          setBulkError(await onDownloadMany(queries));
        }}
      />
      <BulkUploadDialog
        isOpen={bulkUploadOpen}
        onOpenChange={setBulkUploadOpen}
        title="Upload Dynamic Queries"
        description={`Upload up to ${MAX_BULK_UPLOAD_FILES} YAML files. Files whose id already exists will be skipped.`}
        parseFile={(filename, content, seen) => {
          const existingIds = new Set(dynamicQueries.map((query) => getDynamicQueryIdFromFileName(query.file)));
          const parsed = parseUploadedDynamicQuery(filename, content, existingIds, seen);
          return { ...parsed, label: parsed.id };
        }}
        onUpload={async (files) => {
          const uploaded = files.map(({ filename, id, content }) => ({ name: filename, id, content }));
          setBulkError(await onUploadMany(uploaded));
        }}
      />
    </div>
  );
};

export default DynamicQueries;
