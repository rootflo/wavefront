import floConsoleService from "@app/api";
import DeleteConfirmationDialog from "@app/components/DeleteConfirmationDialog";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@app/components/ui/breadcrumb";
import { Button } from "@app/components/ui/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@app/components/ui/tabs";
import {
  useGetAllYamls,
  useGetDatasource,
  useReadYaml,
} from "@app/hooks/data/fetch-hooks";
import { getAllYamlsKey, getDatasourceKey } from "@app/hooks/data/query-keys";
import { useNotifyStore } from "@app/store";
import { YamlReadData } from "@app/types/datasource";
import { validateDynamicQueryYaml } from "@app/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import EditDatasourceDialog from "./EditDatasourceDialog";
import YamlCreation from "./YamlCreation";
import Yamls from "./Yamls";
import YamlView from "./YamlView";

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
  const { data: yamls = [] } = useGetAllYamls(appId, datasourceId);

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedYaml, setSelectedYaml] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);

  // Extract yamlId from selectedYaml (format: "queryId.yaml")
  const yamlId = useMemo(() => {
    if (!selectedYaml) return undefined;
    return selectedYaml.split(".")[0];
  }, [selectedYaml]);

  const { data: yamlData } = useReadYaml(appId, datasourceId, yamlId);

  const [yamlCrud, setYamlCrud] = useState({
    view: false,
    edit: false,
    create: false,
    delete: false,
    execute: false,
  });
  const handleClose = () => {
    setYamlCrud({
      view: false,
      edit: false,
      create: false,
      delete: false,
      execute: false,
    });
    setYamlQueries([]);
    setSelectedYaml(null);
    setYamlExecuteResult([]);
  };
  // Delete state
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Test connection state
  const [testingConnection, setTestingConnection] = useState(false);

  const [yamlCreation, setYamlCreation] = useState<boolean>(false);
  const [yamlContent, setYamlContent] = useState<string>("");
  const [yamlQueries, setYamlQueries] = useState<YamlReadData[]>([]);
  const [yamlName, setYamlName] = useState<string>("");
  const [yamlExecuteResult, setYamlExecuteResult] = useState<
    Record<string, any>[]
  >([]);

  // Update yamlQueries and yamlName when yamlData changes
  useEffect(() => {
    if (yamlData) {
      setYamlName(yamlData.yaml_name || "");
      setYamlQueries(yamlData.yaml_query || []);
    }
  }, [yamlData]);

  const createYaml = async () => {
    try {
      if (!datasourceId || !yamlContent) return;
      const response = await floConsoleService.datasourcesService.createYaml(
        datasourceId,
        yamlContent
      );
      const responseCode = response.data.meta?.code;
      //checking the response code
      if (responseCode === 1) {
        notifySuccess("Yaml created successfully");
        setYamlCreation(false);
        setYamlContent("");
        queryClient.invalidateQueries({
          queryKey: getAllYamlsKey(appId || "", datasourceId),
        });
      } else {
        notifyError("Error while creating yaml");
        return;
      }
    } catch (error) {
      notifyError("Error while creating yaml");
    } finally {
      setYamlCreation(false);
      setYamlContent("");
    }
  };

  const handleYamlEdit = async (yamlContent: string) => {
    if (!datasourceId) return;
    if (yamlContent) {
      const yamlResponse = validateDynamicQueryYaml(yamlContent);
      if (yamlResponse.valid) {
      } else {
        notifyError(yamlResponse.error);
        return;
      }
      const response = await floConsoleService.datasourcesService.createYaml(
        datasourceId,
        yamlContent
      );
      const responseCode = response?.data.meta?.code;
      if (responseCode === 1) {
        notifySuccess("Yaml updated successfully");
        handleClose();
        queryClient.invalidateQueries({
          queryKey: getAllYamlsKey(appId || "", datasourceId),
        });
        if (yamlId) {
          queryClient.invalidateQueries({
            queryKey: ["yaml", appId || "", datasourceId, yamlId],
          });
        }
      } else {
        notifyError("Error while updating yaml");
      }
    }
  };
  const handleYamlDelete = async () => {
    if (!datasourceId || !selectedYaml) return;
    const queryId = selectedYaml.split(".")[0];
    const response = await floConsoleService.datasourcesService.deleteYaml(
      datasourceId,
      queryId
    );
    const responseCode = response?.data.meta?.code;
    if (responseCode === 1) {
      notifySuccess("Yaml deleted successfully");
      handleClose();
      queryClient.invalidateQueries({
        queryKey: getAllYamlsKey(appId || "", datasourceId),
      });
    } else {
      notifyError("Error while deleting yaml");
    }
  };

  const handleYamlExecute = async (params: Record<string, string>) => {
    try {
      setExecuting(true);
      if (!datasourceId || !selectedYaml) return;
      const queryId = selectedYaml.split(".")[0];
      const response = await floConsoleService.datasourcesService.executeYaml(
        datasourceId,
        queryId,
        params
      );
      const responseCode = response?.data.meta?.code;
      if (responseCode === 1) {
        notifySuccess("Yaml executed successfully");
        setYamlExecuteResult(
          (response.data.data as unknown as Record<string, any>[]) || []
        );
      } else {
        notifyError("Error while executing yaml");
      }
    } catch (error) {
      notifyError("Error while executing yaml");
    } finally {
      setExecuting(false);
    }
  };
  const handleEditSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getDatasourceKey(appId || "", datasourceId || ""),
    });
  };

  const handleDelete = async () => {
    if (!datasourceId || !datasource) return;

    setDeleting(true);
    try {
      await floConsoleService.datasourcesService.deleteDatasource(datasourceId);
      notifySuccess("Datasource deleted successfully");
      navigate(`/apps/${appId}/datasources`);
    } catch (error) {
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleTestConnection = async () => {
    if (!datasourceId) return;

    setTestingConnection(true);
    try {
      const result = await floConsoleService.datasourcesService.testDatasource(
        datasourceId
      );

      // Based on updated API, test-connection now returns boolean directly
      const isConnected = (result.data as any) === true;

      if (isConnected) {
        notifySuccess("Connection test successful");
      } else {
        notifyError("Connection test failed");
      }
    } catch (error) {
      notifyError("Failed to test connection");
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <div className="h-full bg-white px-6 pb-[200px] pt-6">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate("/apps")}
                className="hover:text-foreground cursor-pointer"
              >
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
            <p className="text-2xl font-semibold leading-normal text-black">
              {datasource?.name || datasourceId}
            </p>
          </div>
          <div className="flex gap-4">
            <Button onClick={() => setEditDialogOpen(true)} variant="outline">
              Edit
            </Button>
            <Button
              onClick={() => setShowDeleteConfirm(true)}
              variant="destructive"
            >
              Delete
            </Button>
          </div>
        </div>

        <Tabs defaultValue="configuration" className="w-full">
          <TabsList>
            <TabsTrigger className="cursor-pointer" value="configuration">
              Info
            </TabsTrigger>
            <TabsTrigger className="cursor-pointer" value="yamls">
              Dynamic Queries
            </TabsTrigger>
          </TabsList>

          <TabsContent value="configuration" className="mt-6">
            <div className="flex gap-10 pb-5">
              <div className="flex w-1/2 flex-col gap-10">
                <div className="flex flex-col gap-3">
                  <div className="flex justify-between">
                    <div>
                      <Button
                        onClick={handleTestConnection}
                        loading={testingConnection}
                        disabled={testingConnection}
                      >
                        Test Connection
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="yamls" className="mt-6">
            <div className="flex flex-col gap-10">
              <div className="flex w-full justify-end pb-5">
                <Button onClick={() => setYamlCreation(true)}>
                  Create Dynamic Query
                </Button>
              </div>
            </div>
            {/* Yamls component moved inside main container to get pb-10 padding */}
            {yamls && yamls.length > 0 && (
              <Yamls
                yamls={yamls}
                setYamlCrud={setYamlCrud}
                setSelectedYaml={setSelectedYaml}
              />
            )}
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
            message={`Are you sure you want to delete "${
              datasource?.name || ""
            }"? This action cannot be undone.`}
            onConfirm={handleDelete}
            onCancel={() => setShowDeleteConfirm(false)}
            loading={deleting}
            confirmLabel="Delete"
            cancelLabel="Cancel"
          />
        )}

        <YamlCreation
          yamlContent={yamlContent}
          setYamlContent={setYamlContent}
          yamlCreation={yamlCreation}
          setYamlCreation={setYamlCreation}
          createYaml={createYaml}
        />

        <YamlView
          yamlQueries={yamlQueries}
          setYamlCrud={setYamlCrud}
          setYamlQueries={setYamlQueries}
          setSelectedYaml={setSelectedYaml}
          yamlCrud={yamlCrud}
          selectedYaml={selectedYaml}
          yamlName={yamlName}
          handleYamlEdit={handleYamlEdit}
          handleClose={handleClose}
          handleYamlExecute={handleYamlExecute}
          yamlExecuteResult={yamlExecuteResult}
          setYamlExecuteResult={setYamlExecuteResult}
          executing={executing}
        />

        {yamlCrud.delete && selectedYaml && (
          <DeleteConfirmationDialog
            isOpen={showDeleteConfirm}
            title="Delete Yaml"
            message={`Are you sure you want to delete "${selectedYaml}"? This action cannot be undone.`}
            onConfirm={handleYamlDelete}
            onCancel={() => setShowDeleteConfirm(false)}
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
