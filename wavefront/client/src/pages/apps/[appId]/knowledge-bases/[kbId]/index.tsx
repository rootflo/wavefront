import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
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
import {
  getKnowledgeBaseDocumentsKey,
  getKnowledgeBaseIndexStatusKey,
  useGetKnowledgeBase,
  useGetKnowledgeBaseDocuments,
  useGetKnowledgeBaseIndexStatus,
} from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { TrashIcon } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { formatAppName } from '@app/lib/utils';
import IndexStatusSummary from './IndexStatusSummary';
import IndexStatusPill from './IndexStatusPill';

const KnowledgeBaseDetailPage: React.FC = () => {
  const { kbId, app: appId } = useParams<{ kbId: string; app: string }>();

  const [uploading, setUploading] = useState<boolean>(false);
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [documentToDelete, setDocumentToDelete] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const { data: knowledgeBase } = useGetKnowledgeBase(appId, kbId);
  const { data: documents = [], isLoading: loadingDocs } = useGetKnowledgeBaseDocuments(appId, kbId);
  const { data: indexStatus, isLoading: loadingIndexStatus } = useGetKnowledgeBaseIndexStatus(appId, kbId);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // The counts poll while documents are indexing; when they change, refresh
  // the document list too so each row's status follows.
  const indexStatusCounts = JSON.stringify(indexStatus?.counts ?? null);
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: getKnowledgeBaseDocumentsKey(appId || '', kbId || '') });
  }, [indexStatusCounts, queryClient, appId, kbId]);
  const { notifySuccess, notifyError } = useNotifyStore();

  const handleFileUpload = async () => {
    if (!file || !kbId || !appId) {
      notifyError('File, Knowledge Base ID, or Service not available.');
      return;
    }
    setUploading(true);
    try {
      await floConsoleService.knowledgeBaseService.uploadDocument(kbId, file);
      notifySuccess(`${file.name} uploaded successfully.`);
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseDocumentsKey(appId || '', kbId || '') });
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseIndexStatusKey(appId || '', kbId || '') });
      setShowUploadModal(false);
    } catch (error) {
      console.error('File upload failed:', error);
      notifyError(`Failed to upload ${file.name}.`);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!kbId || !appId) {
      notifyError('Knowledge Base ID or Service not available.');
      return;
    }

    try {
      await floConsoleService.knowledgeBaseService.deleteDocument(kbId, documentId);
      notifySuccess('Document deleted successfully.');
      // Invalidate queries to refresh document list
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseDocumentsKey(appId || '', kbId || '') });
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseIndexStatusKey(appId || '', kbId || '') });
    } catch (error) {
      console.error('Document deletion failed:', error);
      notifyError('Failed to delete document.');
    }
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-transparent px-8 pt-8 pb-8">
      <Breadcrumb className="mb-6 shrink-0">
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
                onClick={() => navigate(`/apps/${appId}/knowledge-bases`)}
                className="hover:text-foreground cursor-pointer"
              >
                Knowledge Bases
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{knowledgeBase?.name || kbId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6">
        <div className="flex shrink-0 items-center justify-between">
          <p className="frost-text text-2xl leading-normal font-semibold">
            {formatAppName(knowledgeBase?.name) || 'N/A'}
          </p>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6">
          <div className="flex min-h-0 min-w-0 flex-col gap-3">
            <div className="flex shrink-0 items-center justify-between gap-3">
              <h3 className="frost-text text-lg font-semibold">Documents</h3>
              <Button variant="outline" onClick={() => setShowUploadModal(true)}>
                Upload Document
              </Button>
            </div>

            <IndexStatusSummary status={indexStatus} loading={loadingIndexStatus} />

            {loadingDocs ? (
              <div className="frost-control ring-frost-border flex min-h-0 flex-1 flex-col items-start gap-4 rounded-lg border p-6 ring-1">
                <p className="frost-text-muted text-sm font-medium">Loading</p>
                <div className="frost-text text-sm">Loading documents...</div>
              </div>
            ) : documents.length === 0 ? (
              <div className="frost-control ring-frost-border flex min-h-0 flex-1 flex-col items-start gap-4 rounded-lg border p-6 ring-1">
                <p className="frost-text-muted text-sm font-medium">No Documents</p>
                <div className="frost-text text-sm">No documents uploaded yet.</div>
              </div>
            ) : (
              <div className="frost-table-panel border-frost-border ring-frost-border min-h-0 min-w-0 flex-1 overflow-auto rounded-lg border ring-1">
                <Table className="table-fixed">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[40%]">Document Name</TableHead>
                      <TableHead className="w-[20%]">Status</TableHead>
                      <TableHead className="w-[25%]">Uploaded Date</TableHead>
                      <TableHead className="w-[15%] text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell className="max-w-0 truncate font-medium" title={doc.file_name}>
                          {doc.file_name}
                          <span className="frost-text-muted ml-2 text-xs">({doc.file_type})</span>
                        </TableCell>
                        <TableCell>
                          <IndexStatusPill status={doc.index_status} error={doc.index_error} />
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {dayjs(doc.updated_at).format('DD MMM YYYY')}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setDocumentToDelete(doc.id);
                              setShowDeleteModal(true);
                            }}
                          >
                            <TrashIcon color="#E22F2F" className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upload Document Dialog */}
      <Dialog open={showUploadModal} onOpenChange={setShowUploadModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>Upload a document to this knowledge base</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div>
              <Label htmlFor="documentUpload" className="mb-2">
                Select Document
              </Label>
              <Input
                type="file"
                id="documentUpload"
                accept={
                  knowledgeBase?.type === 'image'
                    ? 'image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff'
                    : '.pdf,.txt,application/pdf,text/plain'
                }
                onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
                disabled={uploading}
                className="frost-control ring-frost-border frost-text file:text-brand w-full cursor-pointer border px-3 py-2 text-sm ring-1 outline-none file:cursor-pointer"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={uploading}>
              Cancel
            </Button>
            <Button onClick={handleFileUpload} disabled={uploading}>
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={showDeleteModal}
        title="Delete Document"
        message="Are you sure you want to delete this document? This action cannot be undone."
        onConfirm={async () => {
          if (documentToDelete) {
            await handleDeleteDocument(documentToDelete);
            setShowDeleteModal(false);
            setDocumentToDelete(null);
          }
        }}
        onCancel={() => {
          setShowDeleteModal(false);
          setDocumentToDelete(null);
        }}
      />
    </div>
  );
};

export default KnowledgeBaseDetailPage;
