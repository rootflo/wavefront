import floConsoleService from "@app/api";
import DeleteConfirmationDialog from "@app/components/DeleteConfirmationDialog";
import { Button } from "@app/components/ui/button";
import { useGetPipelines } from "@app/hooks/data/fetch-hooks";
import { useNotifyStore } from "@app/store";
import { Pipeline, PipelineStatus } from "@app/types/pipeline";
import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router";

const PipelineManagement: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [showMenu, setMenu] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<PipelineStatus | "all">(
    "all"
  );

  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean;
    pipeline: Pipeline | null;
    loading: boolean;
  }>({
    isOpen: false,
    pipeline: null,
    loading: false,
  });

  const {
    data: pipelines = [],
    isLoading,
    error,
  } = useGetPipelines(app, statusFilter);

  const handleCreatePipeline = () => {
    navigate(`/apps/${app}/data-pipelines/create`);
  };

  const handlePipelineClick = (pipeline: Pipeline) => {
    navigate(`/apps/${app}/data-pipelines/${pipeline.pipeline_id}`);
  };

  const handlePause = async (pipeline: Pipeline, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      if (pipeline.status === "published") {
        await floConsoleService.dataPipelineService.pausePipeline(
          "default",
          pipeline.pipeline_id
        );
        notifySuccess(
          `Pipeline "${pipeline.project_name}" paused successfully`
        );
      } else if (pipeline.status === "paused") {
        await floConsoleService.dataPipelineService.unpausePipeline(
          "default",
          pipeline.pipeline_id
        );
        notifySuccess(
          `Pipeline "${pipeline.project_name}" unpaused successfully`
        );
      }
      queryClient.invalidateQueries({ queryKey: ["pipelines", app] });
    } catch (error) {
      notifyError("Failed to update pipeline status");
    }
  };

  const handleTrigger = async (pipeline: Pipeline, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await floConsoleService.dataPipelineService.triggerDagRun(
        "default",
        pipeline.pipeline_id
      );
      notifySuccess(
        `Pipeline "${pipeline.project_name}" triggered successfully`
      );
    } catch (error) {
      notifyError("Failed to trigger pipeline");
    }
  };

  const handleDeletePipeline = (pipeline: Pipeline) => {
    setDeleteDialog({
      isOpen: true,
      pipeline,
      loading: false,
    });
  };

  const confirmDelete = async () => {
    if (!deleteDialog.pipeline) return;

    setDeleteDialog((prev) => ({ ...prev, loading: true }));

    try {
      await floConsoleService.dataPipelineService.deletePipeline(
        "default",
        deleteDialog.pipeline.pipeline_id
      );
      notifySuccess(
        `Pipeline "${deleteDialog.pipeline.project_name}" deleted successfully`
      );

      queryClient.invalidateQueries({ queryKey: ["pipelines", app] });

      setDeleteDialog({
        isOpen: false,
        pipeline: null,
        loading: false,
      });
    } catch (error) {
      console.error("Error deleting pipeline:", error);
      notifyError("Failed to delete pipeline");
      setDeleteDialog((prev) => ({ ...prev, loading: false }));
    }
  };

  const cancelDelete = () => {
    setDeleteDialog({
      isOpen: false,
      pipeline: null,
      loading: false,
    });
  };

  const getStatusBadge = (status: PipelineStatus) => {
    const statusConfig = {
      draft: { bg: "bg-gray-100", text: "text-gray-800", label: "Draft" },
      published: {
        bg: "bg-green-100",
        text: "text-green-800",
        label: "Published",
      },
      paused: { bg: "bg-yellow-100", text: "text-yellow-800", label: "Paused" },
    };

    const config = statusConfig[status];
    return (
      <span
        className={clsx(
          "rounded-full px-3 py-1 text-xs font-medium",
          config.bg,
          config.text
        )}
      >
        {config.label}
      </span>
    );
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="mx-auto max-w-7xl">
          <div className="flex justify-center">
            <div className="text-gray-500">Loading pipelines...</div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="mx-auto max-w-7xl">
          <div className="flex justify-center">
            <div className="text-red-500">
              Error loading pipelines. Please try again.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Pipeline Management
            </h1>
            <p className="mt-2 text-gray-600">
              Manage and configure DBT pipelines
            </p>
          </div>
          <Button onClick={handleCreatePipeline}>Create Pipeline</Button>
        </div>

        <div className="mb-4 flex gap-2">
          {(["all", "draft", "published", "paused"] as const).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={clsx(
                "rounded-lg px-4 py-2 text-sm font-medium",
                statusFilter === status
                  ? "bg-black text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              )}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>

        {pipelines.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <p className="text-gray-500">No pipelines found</p>
            <button
              onClick={handleCreatePipeline}
              className="mt-4 text-sm text-blue-600 hover:text-blue-800"
            >
              Create your first pipeline
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {pipelines.map((pipeline) => (
              <div
                key={pipeline.pipeline_id}
                className="cursor-pointer rounded-lg border border-gray-200 bg-white p-5 hover:shadow-md"
                onClick={() => handlePipelineClick(pipeline)}
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {pipeline.project_name}
                    </h3>
                    {pipeline.description && (
                      <p className="mt-1 text-sm text-gray-600">
                        {pipeline.description}
                      </p>
                    )}
                  </div>
                  <div
                    className="relative"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenu(
                        showMenu === pipeline.pipeline_id
                          ? null
                          : pipeline.pipeline_id
                      );
                    }}
                  >
                    {showMenu === pipeline.pipeline_id && (
                      <div className="absolute right-0 z-10 mt-2 w-48 rounded-lg bg-white p-2 shadow-lg">
                        {pipeline.status === "published" && (
                          <>
                            <button
                              className="w-full rounded-lg p-2 text-left text-sm hover:bg-gray-100"
                              onClick={(e) => handlePause(pipeline, e)}
                            >
                              Pause
                            </button>
                            <button
                              className="w-full rounded-lg p-2 text-left text-sm hover:bg-gray-100"
                              onClick={(e) => handleTrigger(pipeline, e)}
                            >
                              Trigger
                            </button>
                          </>
                        )}
                        {pipeline.status === "paused" && (
                          <button
                            className="w-full rounded-lg p-2 text-left text-sm hover:bg-gray-100"
                            onClick={(e) => handlePause(pipeline, e)}
                          >
                            Unpause
                          </button>
                        )}
                        <button
                          className="w-full rounded-lg p-2 text-left text-sm text-red-600 hover:bg-gray-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeletePipeline(pipeline);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="mb-4 flex items-center gap-2">
                  {getStatusBadge(pipeline.status)}
                </div>

                <div className="space-y-2 text-sm text-gray-600">
                  {pipeline.schedule_interval && (
                    <div>
                      <span className="font-medium">Schedule:</span>{" "}
                      {pipeline.schedule_interval}
                    </div>
                  )}
                  <div>
                    <span className="font-medium">Updated:</span>{" "}
                    {new Date(pipeline.updated_at).toLocaleDateString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <DeleteConfirmationDialog
        isOpen={deleteDialog.isOpen}
        title="Delete Pipeline"
        message={
          deleteDialog.pipeline
            ? `Are you sure you want to delete "${deleteDialog.pipeline.project_name}"? This action cannot be undone and will remove all associated files and resources.`
            : ""
        }
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
        loading={deleteDialog.loading}
      />
    </div>
  );
};

export default PipelineManagement;
