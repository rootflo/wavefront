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
import { Label } from '@app/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { useGetAllDynamicQueries, useGetDatasource, useReadDynamicQuery } from '@app/hooks/data/fetch-hooks';
import { getAllDynamicQueriesKey, getDatasourceKey, readDynamicQueryKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, createZipBlob, downloadBlobFile, validateDynamicQueryYaml } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { DynamicQuery, DynamicQueryItem } from '@app/types/datasource';
import { useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import EditDatasourceDialog from './EditDatasourceDialog';
import DynamicQueryCreation from './DynamicQueryCreation';
import DynamicQueries from './DynamicQueries';
import DynamicQueryView from './DynamicQueryView';
import { buildDynamicQueryYaml, downloadTextFile, getDynamicQueryYamlFilename } from './dynamic-query-utils';

const DATASOURCE_TYPE_LABELS: Record<string, string> = {
  gcp_bigquery: 'Google BigQuery',
  aws_redshift: 'AWS Redshift',
  postgres: 'PostgreSQL',
  mssql: 'Microsoft SQL Server',
};

const formatDatasourceDate = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
};

const DatasourceDetail: React.FC = () => {
  const { app: appId, datasourceId } = useParams<{
    app: string;
    datasourceId: string;
  }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  // Use hooks for GET requests
  const { data: datasource } = useGetDatasource(appId, datasourceId);
  const { data: dynamicQueries = [], isLoading: dynamicQueriesLoading } = useGetAllDynamicQueries(appId, datasourceId);

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedQuery, setSelectedQuery] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);

  const queryId = useMemo(() => {
    if (!selectedQuery) return undefined;
    return selectedQuery.split('.')[0];
  }, [selectedQuery]);

  const { data: queryData } = useReadDynamicQuery(appId, datasourceId, queryId);

  const [queryCrud, setQueryCrud] = useState({
    view: false,
    edit: false,
    create: false,
    delete: false,
    execute: false,
  });
  const handleClose = () => {
    setQueryCrud({
      view: false,
      edit: false,
      create: false,
      delete: false,
      execute: false,
    });
    setQueryItems([]);
    setSelectedQuery(null);
    setExecuteResult([]);
  };
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const [testingConnection, setTestingConnection] = useState(false);

  const [queryCreation, setQueryCreation] = useState<boolean>(false);
  const [queryContent, setQueryContent] = useState<string>('');
  const [queryItems, setQueryItems] = useState<DynamicQueryItem[]>([]);
  const [queryName, setQueryName] = useState<string>('');
  const [executeResult, setExecuteResult] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    if (queryData) {
      setQueryName(queryData.yaml_name || '');
      setQueryItems(queryData.yaml_query || []);
    }
  }, [queryData]);

  const createDynamicQuery = async () => {
    try {
      if (!datasourceId || !queryContent) return;
      const response = await floConsoleService.datasourcesService.createDynamicQuery(datasourceId, queryContent);
      const responseCode = response.data.meta?.code;
      if (responseCode === 1) {
        notifySuccess('Dynamic query created successfully');
        setQueryCreation(false);
        setQueryContent('');
        queryClient.invalidateQueries({
          queryKey: getAllDynamicQueriesKey(appId || '', datasourceId),
        });
      } else {
        notifyError('Error while creating dynamic query');
      }
    } catch {
      notifyError('Error while creating dynamic query');
    }
  };

  const handleDynamicQueryEdit = async (content: string) => {
    if (!datasourceId) return;
    if (content) {
      const queryResponse = validateDynamicQueryYaml(content);
      if (!queryResponse.valid) {
        notifyError(queryResponse.error);
        return;
      }
      const response = await floConsoleService.datasourcesService.createDynamicQuery(datasourceId, content);
      const responseCode = response?.data.meta?.code;
      if (responseCode === 1) {
        notifySuccess('Dynamic query updated successfully');
        handleClose();
        queryClient.invalidateQueries({
          queryKey: getAllDynamicQueriesKey(appId || '', datasourceId),
        });
        if (queryId) {
          queryClient.invalidateQueries({
            queryKey: readDynamicQueryKey(appId || '', datasourceId, queryId),
          });
        }
      } else {
        notifyError('Error while updating dynamic query');
      }
    }
  };
  const handleDynamicQueryDelete = async () => {
    if (!datasourceId || !selectedQuery) return;
    const selectedQueryId = selectedQuery.split('.')[0];
    const response = await floConsoleService.datasourcesService.deleteDynamicQuery(datasourceId, selectedQueryId);
    const responseCode = response?.data.meta?.code;
    if (responseCode === 1) {
      notifySuccess('Dynamic query deleted successfully');
      handleClose();
      queryClient.invalidateQueries({
        queryKey: getAllDynamicQueriesKey(appId || '', datasourceId),
      });
    } else {
      notifyError('Error while deleting dynamic query');
    }
  };

  const handleDynamicQueryDownload = async (query: DynamicQuery) => {
    try {
      const file = await fetchDynamicQueryYaml(query);
      if (!file) {
        notifyError('Failed to download dynamic query');
        return;
      }
      downloadTextFile(file.filename, file.content);
    } catch {
      notifyError('Failed to download dynamic query');
    }
  };

  const handleDynamicQueryDownloadMany = async (queries: DynamicQuery[]) => {
    const files: { filename: string; content: string }[] = [];
    const failed: string[] = [];
    for (const query of queries) {
      const filename = getDynamicQueryYamlFilename(query.file);
      try {
        const file = await fetchDynamicQueryYaml(query);
        if (file) files.push(file);
        else failed.push(filename);
      } catch {
        failed.push(filename);
      }
    }

    if (files.length === 0) {
      return `Failed to download dynamic queries: ${failed.join(', ')}`;
    }

    downloadBlobFile('dynamic-queries.zip', createZipBlob(files));
    return failed.length > 0 ? `Failed to download: ${failed.join(', ')}` : '';
  };

  const handleDynamicQueryUploadMany = async (files: { name: string; id: string; content: string }[]) => {
    if (!datasourceId) return '';

    let created = 0;
    const failed: string[] = [];
    for (const file of files) {
      try {
        const response = await floConsoleService.datasourcesService.createDynamicQuery(datasourceId, file.content);
        if (response.data.meta?.code === 1) {
          created += 1;
        } else {
          failed.push(file.name);
        }
      } catch {
        failed.push(file.name);
      }
    }

    queryClient.invalidateQueries({
      queryKey: getAllDynamicQueriesKey(appId || '', datasourceId),
    });

    if (created > 0) {
      notifySuccess(`Created ${created} dynamic ${created === 1 ? 'query' : 'queries'}`);
    }
    return failed.length > 0 ? `Failed to create dynamic queries: ${failed.join(', ')}` : '';
  };

  const fetchDynamicQueryYaml = async (query: DynamicQuery) => {
    if (!datasourceId) return null;
    const queryId = query.file.split('.')[0];
    const response = await floConsoleService.datasourcesService.readDynamicQuery(datasourceId, queryId);
    const data = response.data?.data;
    if (!data) return null;
    const yamlContent = buildDynamicQueryYaml(query.file, data.yaml_name || '', data.yaml_query || []);
    if (!yamlContent) return null;
    return { filename: getDynamicQueryYamlFilename(query.file), content: yamlContent };
  };

  const handleDynamicQueryExecute = async (params: Record<string, string>) => {
    try {
      setExecuting(true);
      if (!datasourceId || !selectedQuery) return;
      const selectedQueryId = selectedQuery.split('.')[0];
      const response = await floConsoleService.datasourcesService.executeDynamicQuery(
        datasourceId,
        selectedQueryId,
        params
      );
      const responseCode = response?.data.meta?.code;
      if (responseCode === 1) {
        notifySuccess('Dynamic query executed successfully');
        setExecuteResult((response.data.data as unknown as Record<string, unknown>[]) || []);
      } else {
        notifyError('Error while executing dynamic query');
      }
    } catch {
      notifyError('Error while executing dynamic query');
    } finally {
      setExecuting(false);
    }
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getDatasourceKey(appId || '', datasourceId || ''),
    });
  };

  const handleDelete = async () => {
    if (!datasourceId || !datasource) return;

    setDeleting(true);
    try {
      await floConsoleService.datasourcesService.deleteDatasource(datasourceId);
      notifySuccess('Datasource deleted successfully');
      navigate(`/apps/${appId}/datasources`);
    } catch {
      console.error('Error deleting datasource');
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const handleTestConnection = async () => {
    if (!datasourceId) return;

    setTestingConnection(true);
    try {
      const result = await floConsoleService.datasourcesService.testDatasource(datasourceId);

      // Based on updated API, test-connection now returns boolean directly
      const isConnected = (result.data as unknown) === true;

      if (isConnected) {
        notifySuccess('Connection test successful');
      } else {
        notifyError('Connection test failed');
      }
    } catch {
      notifyError('Failed to test connection');
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <div className="h-full bg-white px-6 pt-6 pb-[200px]">
      <Breadcrumb className="mb-6">
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
                onClick={() => navigate(`/apps/${appId}/datasources`)}
                className="hover:text-foreground cursor-pointer"
              >
                Datasources
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{datasource?.name || datasourceId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-3">
            <p className="text-2xl leading-normal font-semibold text-black">{datasource?.name || datasourceId}</p>
          </div>
          <div className="flex gap-4">
            <Button onClick={() => setEditDialogOpen(true)} variant="outline">
              Edit
            </Button>
            <Button onClick={() => setShowDeleteConfirm(true)} variant="destructive">
              Delete
            </Button>
          </div>
        </div>

        <Tabs defaultValue="configuration" className="w-full">
          <TabsList>
            <TabsTrigger className="cursor-pointer" value="configuration">
              Info
            </TabsTrigger>
            <TabsTrigger className="cursor-pointer" value="dynamic-queries">
              Dynamic Queries
            </TabsTrigger>
          </TabsList>

          <TabsContent value="configuration" className="mt-6">
            <div className="grid w-full gap-6 lg:grid-cols-3">
              <div className="flex flex-col gap-6 lg:col-span-2">
                <div className="flex flex-col gap-2">
                  <Label>Description</Label>
                  <p className="text-sm text-gray-900">{datasource?.description || '—'}</p>
                </div>
                <div>
                  <Button onClick={handleTestConnection} loading={testingConnection} disabled={testingConnection}>
                    Test Connection
                  </Button>
                </div>
              </div>

              {datasource && (
                <div className="rounded-lg border border-[#EFF0F1]">
                  <div className="border-b border-[#EFF0F1] px-6 py-4">
                    <h2 className="text-lg font-semibold text-gray-900">Metadata</h2>
                  </div>
                  <dl className="space-y-4 p-6">
                    <div>
                      <dt className="text-xs font-medium text-gray-500">Datasource ID</dt>
                      <dd className="mt-1 flex items-center gap-1">
                        <span className="truncate font-mono text-sm text-gray-900" title={datasource.id}>
                          {datasource.id}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Copy ID"
                          onClick={() => void handleCopyId(datasource.id)}
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-gray-500">Type</dt>
                      <dd className="mt-1 text-sm text-gray-900">
                        {DATASOURCE_TYPE_LABELS[datasource.type] || datasource.type || '—'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-gray-500">Created At</dt>
                      <dd className="mt-1 text-sm text-gray-900">{formatDatasourceDate(datasource.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-gray-500">Updated At</dt>
                      <dd className="mt-1 text-sm text-gray-900">{formatDatasourceDate(datasource.updated_at)}</dd>
                    </div>
                  </dl>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="dynamic-queries" className="mt-6">
            <DynamicQueries
              dynamicQueries={dynamicQueries}
              isLoading={dynamicQueriesLoading}
              onCreate={() => setQueryCreation(true)}
              onDownload={handleDynamicQueryDownload}
              onDownloadMany={handleDynamicQueryDownloadMany}
              onUploadMany={handleDynamicQueryUploadMany}
              setQueryCrud={setQueryCrud}
              setSelectedQuery={setSelectedQuery}
            />
          </TabsContent>
        </Tabs>

        {/* Edit Datasource Dialog */}
        {appId && datasource && (
          <EditDatasourceDialog
            isOpen={editDialogOpen}
            onOpenChange={setEditDialogOpen}
            appId={appId}
            datasource={datasource}
            onSuccess={handleEditSuccess}
          />
        )}

        {/* Delete Confirmation Dialog */}
        {showDeleteConfirm && (
          <DeleteConfirmationDialog
            isOpen={showDeleteConfirm}
            title="Delete Datasource"
            message={`Are you sure you want to delete "${datasource?.name || ''}"? This action cannot be undone.`}
            onConfirm={handleDelete}
            onCancel={() => setShowDeleteConfirm(false)}
            loading={deleting}
            confirmLabel="Delete"
            cancelLabel="Cancel"
          />
        )}

        <DynamicQueryCreation
          queryContent={queryContent}
          setQueryContent={setQueryContent}
          isOpen={queryCreation}
          setIsOpen={setQueryCreation}
          onCreate={createDynamicQuery}
        />

        <DynamicQueryView
          queryItems={queryItems}
          setQueryCrud={setQueryCrud}
          setQueryItems={setQueryItems}
          setSelectedQuery={setSelectedQuery}
          queryCrud={queryCrud}
          selectedQuery={selectedQuery}
          queryName={queryName}
          handleDynamicQueryEdit={handleDynamicQueryEdit}
          handleClose={handleClose}
          handleDynamicQueryExecute={handleDynamicQueryExecute}
          executeResult={executeResult}
          setExecuteResult={setExecuteResult}
          executing={executing}
        />

        {queryCrud.delete && selectedQuery && (
          <DeleteConfirmationDialog
            isOpen={queryCrud.delete}
            title="Delete Dynamic Query"
            message={`Are you sure you want to delete "${selectedQuery}"? This action cannot be undone.`}
            onConfirm={handleDynamicQueryDelete}
            onCancel={handleClose}
            loading={deleting}
            confirmLabel="Delete"
            cancelLabel="Cancel"
          />
        )}
      </div>
    </div>
  );
};

export default DatasourceDetail;
