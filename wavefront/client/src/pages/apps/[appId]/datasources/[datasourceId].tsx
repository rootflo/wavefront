import floConsoleService from '@app/api';
import { DynamicQueryRunOptions } from '@app/types/datasource';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import DetailActions from '@app/components/DetailActions';
import MobileBackButton from '@app/components/MobileBackButton';
import { PageActionsContext } from '@app/components/PageActionsContext';
import PageTitle from '@app/components/PageTitle';
import { Button } from '@app/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { useGetAllDynamicQueries, useGetDatasource, useReadDynamicQuery } from '@app/hooks';
import { getAllDynamicQueriesKey } from '@app/hooks/data/query-keys';
import { copyToClipboard } from '@app/utils/clipboard';
import { createZipBlob, downloadBlobFile } from '@app/utils/download';
import { cn } from '@app/lib/utils';
import { extractErrorMessage } from '@app/lib/errors';
import { validateDynamicQueryYaml } from './dynamic-query-utils';
import { formatAppName } from '@app/utils/string-formatting';
import { useNotifyStore } from '@app/store';
import { DynamicQuery, DynamicQueryItem } from '@app/types/datasource';
import { useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { isFileStorageType } from './datasource-types';
import EditDatasourceDialog from './EditDatasourceDialog';
import FileStoragePanel from './FileStoragePanel';
import { useConnectionTest } from './connection-test';
import DatasourceActivity from './DatasourceActivity';
import DatasourceDataBrowser from './DatasourceDataBrowser';
import DatasourceInfo from './DatasourceInfo';
import DatasourceOperations from './DatasourceOperations';
import DynamicQueryCreation from './DynamicQueryCreation';
import DynamicQueries from './DynamicQueries';
import DynamicQueryView from './DynamicQueryView';
import { buildDynamicQueryYaml, downloadTextFile, getDynamicQueryYamlFilename } from './dynamic-query-utils';
import { useDeleteDatasource, useDeleteDynamicQuery, useSaveDynamicQuery } from '@app/hooks';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const DatasourceDetail: React.FC = () => {
  const { app: appId, datasourceId } = useParams<{
    app: string;
    datasourceId: string;
  }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const deleteDatasource = useDeleteDatasource(appId);
  const saveDynamicQuery = useSaveDynamicQuery(appId, datasourceId);
  const deleteDynamicQuery = useDeleteDynamicQuery(appId, datasourceId);

  // Use hooks for GET requests
  const { data: datasource, isLoading: datasourceLoading } = useGetDatasource(appId, datasourceId);
  const isFileStorage = isFileStorageType(datasource?.type);
  // File storage datasources have no SQL surface, so skip the dynamic queries fetch.
  const { data: dynamicQueries = [], isLoading: dynamicQueriesLoading } = useGetAllDynamicQueries(
    appId,
    datasource && !isFileStorage ? datasourceId : undefined
  );

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedQuery, setSelectedQuery] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [exporting, setExporting] = useState(false);
  // Where the active tab's ListHeader puts its controls, beside the tab bar.
  const [tabActionsSlot, setTabActionsSlot] = useState<HTMLElement | null>(null);

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
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const [testingConnection, setTestingConnection] = useState(false);
  const [lastTest, recordTest] = useConnectionTest(datasourceId);

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

  // Async because DynamicQueryCreation awaits it to show its own saving state
  const createDynamicQuery = async () => {
    if (!datasourceId || !queryContent) return;
    try {
      await saveDynamicQuery.mutateAsync({ content: queryContent });
      setQueryCreation(false);
      setQueryContent('');
    } catch {
      // useSaveDynamicQuery has already shown the error
    }
  };

  const handleDynamicQueryEdit = (content: string) => {
    if (!datasourceId || !content) return;
    const queryResponse = validateDynamicQueryYaml(content);
    if (!queryResponse.valid) {
      notifyError(queryResponse.error);
      return;
    }
    saveDynamicQuery.mutate({ content, isUpdate: true, queryId }, { onSuccess: handleClose });
  };
  const handleDynamicQueryDelete = () => {
    if (!datasourceId || !selectedQuery) return;
    deleteDynamicQuery.mutate(selectedQuery.split('.')[0], { onSuccess: handleClose });
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

  const handleDynamicQueryExecute = async (params: Record<string, string>, options: DynamicQueryRunOptions) => {
    try {
      setExecuting(true);
      if (!datasourceId || !selectedQuery) return;
      const selectedQueryId = selectedQuery.split('.')[0];
      const response = await floConsoleService.datasourcesService.executeDynamicQuery(
        datasourceId,
        selectedQueryId,
        params,
        options
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

  const handleDynamicQueryExport = async (params: Record<string, string>, options: DynamicQueryRunOptions) => {
    if (!datasourceId || !selectedQuery) return;
    setExporting(true);
    try {
      const response = await floConsoleService.datasourcesService.exportDynamicQuery(
        datasourceId,
        selectedQuery.split('.')[0],
        params,
        options
      );
      const exportUrl = response.data?.data?.export_url;
      if (!exportUrl) {
        notifyError('No export link was returned');
        return;
      }
      // A presigned link to the stored CSV; opening it downloads the file.
      window.open(exportUrl, '_blank', 'noopener');
      notifySuccess('Export ready, downloading CSV');
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to export the query');
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = () => {
    if (!datasourceId || !datasource) return;
    deleteDatasource.mutate(datasourceId, {
      onSuccess: () => navigate(`/apps/${appId}/datasources`),
      onSettled: () => setShowDeleteConfirm(false),
    });
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

      recordTest(isConnected);
      if (isConnected) {
        notifySuccess('Connection test successful');
      } else {
        notifyError('Connection test failed');
      }
    } catch {
      recordTest(false);
      notifyError('Failed to test connection');
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-4 max-md:overflow-y-auto sm:p-8">
      <PageBreadcrumb
        className="shrink-0"
        items={[
          { label: 'Datasources', to: `/apps/${appId}/datasources` },
          { label: datasource?.name || datasourceId, loading: datasourceLoading },
        ]}
      />

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden">
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <MobileBackButton to={`/apps/${appId}/datasources`} label="Back to datasources" />
              <PageTitle loading={datasourceLoading}>{formatAppName(datasource?.name || datasourceId)}</PageTitle>
            </div>
          </div>
          <DetailActions
            onEdit={() => setEditDialogOpen(true)}
            onDelete={() => setShowDeleteConfirm(true)}
            leading={
              <Button
                variant="outline"
                onClick={() => void handleTestConnection()}
                loading={testingConnection}
                disabled={testingConnection || !datasource}
                title={
                  lastTest
                    ? `${lastTest.ok ? 'Connected' : 'Connection failed'} when last tested, ${new Date(lastTest.at).toLocaleString()}`
                    : 'Not tested yet'
                }
              >
                {testingConnection ? null : (
                  <span
                    aria-hidden
                    className={cn(
                      'size-2 rounded-full',
                      !lastTest ? 'bg-frost-text-subtle' : lastTest.ok ? 'bg-emerald-500' : 'bg-rose-500'
                    )}
                  />
                )}
                Test connection
              </Button>
            }
          />
        </div>

        <PageActionsContext.Provider value={{ element: tabActionsSlot }}>
          <Tabs defaultValue="configuration" className="flex min-h-0 flex-1 flex-col overflow-hidden">
            {/* The tab bar doubles as the header row: a tab's search and buttons (Dynamic Queries) sit on its right. */}
            <div className="flex shrink-0 flex-col gap-3 md:flex-row md:items-center md:justify-between md:gap-4">
              <TabsList className="shrink-0">
                <TabsTrigger className="cursor-pointer" value="configuration">
                  Info
                </TabsTrigger>
                {isFileStorage ? (
                  <TabsTrigger className="cursor-pointer" value="files">
                    Files
                  </TabsTrigger>
                ) : (
                  <>
                    <TabsTrigger className="cursor-pointer" value="data">
                      Data
                    </TabsTrigger>
                    <TabsTrigger className="cursor-pointer" value="operations">
                      Operations
                    </TabsTrigger>
                    <TabsTrigger className="cursor-pointer" value="dynamic-queries">
                      Dynamic Queries
                    </TabsTrigger>
                  </>
                )}
                <TabsTrigger className="cursor-pointer" value="activity">
                  Activity
                </TabsTrigger>
              </TabsList>
              <div ref={setTabActionsSlot} className="min-w-0 md:shrink-0" />
            </div>

            <TabsContent value="configuration" className="mt-6 min-h-0 flex-1 overflow-auto">
              {datasource && (
                <DatasourceInfo
                  datasource={datasource}
                  isFileStorage={isFileStorage}
                  dynamicQueryCount={dynamicQueries.length}
                  lastTest={lastTest}
                  testing={testingConnection}
                  onTest={() => void handleTestConnection()}
                  onCopyId={(id) => void handleCopyId(id)}
                />
              )}
            </TabsContent>

            {!isFileStorage && (
              <TabsContent
                value="data"
                className="mt-6 min-h-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col"
              >
                {datasourceId && <DatasourceDataBrowser datasourceId={datasourceId} />}
              </TabsContent>
            )}

            {isFileStorage && datasource && datasourceId && (
              <TabsContent
                value="files"
                className="mt-6 min-h-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col"
              >
                <FileStoragePanel datasourceId={datasourceId} />
              </TabsContent>
            )}

            <TabsContent
              value="operations"
              className="mt-6 min-h-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col"
            >
              {datasourceId && <DatasourceOperations datasourceId={datasourceId} />}
            </TabsContent>

            <TabsContent
              value="dynamic-queries"
              className="mt-6 min-h-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col"
            >
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
            <TabsContent
              value="activity"
              className="mt-6 min-h-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col"
            >
              {datasourceId && <DatasourceActivity datasourceId={datasourceId} />}
            </TabsContent>
          </Tabs>
        </PageActionsContext.Provider>
      </div>

      {/* Edit Datasource Dialog */}
      {appId && datasource && (
        <EditDatasourceDialog
          isOpen={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          appId={appId}
          datasource={datasource}
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
          loading={deleteDatasource.isPending}
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
        handleDynamicQueryExport={handleDynamicQueryExport}
        exporting={exporting}
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
          loading={deleteDynamicQuery.isPending}
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      )}
    </div>
  );
};

export default DatasourceDetail;
