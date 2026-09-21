import floConsoleService from '@app/api';
import BulkDownloadDialog from '@app/components/BulkDownloadDialog';
import BulkUploadDialog, { MAX_BULK_UPLOAD_FILES } from '@app/components/BulkUploadDialog';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ErrorBanner } from '@app/components/Banner';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetMessageProcessors } from '@app/hooks';
import { getMessageProcessorsKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, createZipBlob, downloadBlobFile, downloadTextFile, getYamlFilename } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { MessageProcessorListItem } from '@app/types/message-processor';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, Download, Trash2 } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateFunctionDialog from './CreateFunctionDialog';
import { parseUploadedFunction } from './function-utils';

const formatCreatedAt = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
};

const FunctionsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<MessageProcessorListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [bulkDownloadOpen, setBulkDownloadOpen] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState('');

  const { selectedApp } = useDashboardStore();
  const { notifySuccess, notifyError } = useNotifyStore();

  const { data: processors = [], isLoading: loading } = useGetMessageProcessors(appId);

  const filteredProcessors = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const filtered = term
      ? processors.filter(
          (processor) =>
            processor.name.toLowerCase().includes(term) ||
            processor.id.toLowerCase().includes(term) ||
            (processor.description || '').toLowerCase().includes(term)
        )
      : processors;

    return [...filtered].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [processors, searchTerm]);

  const handleCreateProcessor = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getMessageProcessorsKey(appId || ''),
    });
    setCreateDialogOpen(false);
  };

  const handleProcessorClick = (processorId: string) => {
    navigate(`/apps/${appId}/functions/${processorId}`);
  };

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const fetchFunctionYaml = async (processor: MessageProcessorListItem) => {
    const response = await floConsoleService.messageProcessorService.getMessageProcessor(processor.id);
    const data = response.data?.data?.processor;
    if (!data?.yaml_content) return null;
    return {
      filename: getYamlFilename(processor.name),
      content: data.yaml_content,
    };
  };

  const handleFunctionDownload = async (processor: MessageProcessorListItem) => {
    setDownloadingId(processor.id);
    try {
      const file = await fetchFunctionYaml(processor);
      if (!file) {
        notifyError('Failed to download function');
        return;
      }
      downloadTextFile(file.filename, file.content);
    } catch {
      notifyError('Failed to download function');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleFunctionDownloadMany = async (selected: MessageProcessorListItem[]) => {
    const files: { filename: string; content: string }[] = [];
    const failed: string[] = [];
    for (const processor of selected) {
      const filename = getYamlFilename(processor.name);
      try {
        const file = await fetchFunctionYaml(processor);
        if (file) files.push(file);
        else failed.push(filename);
      } catch {
        failed.push(filename);
      }
    }

    if (files.length === 0) {
      setBulkError(`Failed to download functions: ${failed.join(', ')}`);
      return;
    }

    downloadBlobFile('functions.zip', createZipBlob(files));
    setBulkError(failed.length > 0 ? `Failed to download: ${failed.join(', ')}` : '');
  };

  const handleFunctionUploadMany = async (files: { name: string; description?: string; content: string }[]) => {
    let created = 0;
    const failed: string[] = [];
    for (const file of files) {
      try {
        const response = await floConsoleService.messageProcessorService.createMessageProcessor({
          name: file.name,
          yaml_content: file.content,
          description: file.description,
        });
        if (response.data?.meta?.status === 'failure') {
          failed.push(file.name);
        } else {
          created += 1;
        }
      } catch {
        failed.push(file.name);
      }
    }

    queryClient.invalidateQueries({
      queryKey: getMessageProcessorsKey(appId || ''),
    });

    if (created > 0) {
      notifySuccess(`Created ${created} ${created === 1 ? 'function' : 'functions'}`);
    }
    setBulkError(failed.length > 0 ? `Failed to create functions: ${failed.join(', ')}` : '');
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.messageProcessorService.deleteMessageProcessor(deleteItem.id);
      notifySuccess('Function deleted successfully');
      queryClient.invalidateQueries({
        queryKey: getMessageProcessorsKey(appId || ''),
      });
      setDeleteItem(null);
    } catch {
      notifyError('Failed to delete function');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-8">
      <Breadcrumb className="mb-4 shrink-0">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${appId}/functions`)}
                className="hover:text-foreground cursor-pointer"
              >
                Functions
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full shrink-0 items-start justify-between">
        <div>
          <h1 className="frost-text text-3xl font-bold">Functions</h1>
          <p className="frost-text-muted mt-2">Manage and configure functions for {selectedApp?.app_name}</p>
        </div>
        <div className="flex items-center gap-3">
          <Input
            className="w-[200px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button variant="outline" onClick={() => setBulkDownloadOpen(true)} disabled={processors.length === 0}>
            Download
          </Button>
          <Button variant="outline" onClick={() => setBulkUploadOpen(true)}>
            Upload
          </Button>
          <Button onClick={handleCreateProcessor}>Create Function</Button>
        </div>
      </div>

      {bulkError ? <ErrorBanner message={bulkError} onDismiss={() => setBulkError('')} /> : null}

      {loading ? (
        <p className="frost-text-muted text-sm">Loading functions...</p>
      ) : filteredProcessors.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No functions found"
            description="Get started by creating your first function"
            actionText="Create Function"
            onActionClick={handleCreateProcessor}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredProcessors.map((processor) => (
                <TableRow
                  key={processor.id}
                  className="cursor-pointer"
                  onClick={() => handleProcessorClick(processor.id)}
                >
                  <TableCell className="max-w-[220px] truncate font-medium" title={processor.name}>
                    {processor.name}
                  </TableCell>
                  <TableCell className="max-w-[240px]" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      <span className="truncate font-mono text-xs" title={processor.id}>
                        {processor.id}
                      </span>
                      <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(processor.id)}>
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[280px] truncate text-sm" title={processor.description || ''}>
                    {processor.description || '—'}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{formatCreatedAt(processor.created_at)}</TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Download"
                        loading={downloadingId === processor.id}
                        onClick={() => void handleFunctionDownload(processor)}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" title="Delete" onClick={() => setDeleteItem(processor)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Function"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteItem(null)}
        loading={deleting}
      />

      {appId && (
        <CreateFunctionDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}

      <BulkDownloadDialog
        isOpen={bulkDownloadOpen}
        onOpenChange={setBulkDownloadOpen}
        title="Download Functions"
        description="Select functions to download. Each file is named after the function."
        emptyLabel="No functions available"
        items={processors}
        getItemId={(processor) => processor.id}
        getItemLabel={(processor) => getYamlFilename(processor.name)}
        onDownload={handleFunctionDownloadMany}
      />
      <BulkUploadDialog
        isOpen={bulkUploadOpen}
        onOpenChange={setBulkUploadOpen}
        title="Upload Functions"
        description={`Upload up to ${MAX_BULK_UPLOAD_FILES} YAML files. The file name (without .yaml) is used as the function name. Only valid function YAML files are accepted. Files whose name already exists will be skipped.`}
        parseFile={(filename, content, seen) => {
          const existingNames = new Set(processors.map((processor) => processor.name.trim().toLowerCase()));
          const parsed = parseUploadedFunction(filename, content, existingNames, seen);
          return { ...parsed, label: parsed.name };
        }}
        onUpload={(files) =>
          handleFunctionUploadMany(files.map(({ name, description, content }) => ({ name, description, content })))
        }
      />
    </div>
  );
};

export default FunctionsManagement;
