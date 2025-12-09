import floConsoleService from "@app/api";
import DeleteConfirmationDialog from "@app/components/DeleteConfirmationDialog";
import { EmptyStateCard } from "@app/components/EmptyCard";
import FunctionCard from "@app/components/FunctionCard";
import { ResourceCardSkeleton } from "@app/components/ResourceCard";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from "@app/components/ui/breadcrumb";
import { Button } from "@app/components/ui/button";
import { Input } from "@app/components/ui/input";
import { useGetMessageProcessors } from "@app/hooks";
import { getMessageProcessorsKey } from "@app/hooks/data/query-keys";
import { useDashboardStore, useNotifyStore } from "@app/store";
import { MessageProcessorListItem } from "@app/types/message-processor";
import { useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router";
import CreateFunctionDialog from "./CreateFunctionDialog";

const FunctionsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [deleteItem, setDeleteItem] = useState<MessageProcessorListItem | null>(
    null
  );
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { selectedApp } = useDashboardStore();
  const { notifySuccess } = useNotifyStore();

  // Fetch message processors
  const { data: processors = [], isLoading: loading } =
    useGetMessageProcessors(appId);

  const filteredProcessors = processors.filter(
    (processor) =>
      processor.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      processor.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateProcessor = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getMessageProcessorsKey(appId || ""),
    });
    setCreateDialogOpen(false);
  };

  const handleProcessorClick = (processorId: string) => {
    navigate(`/apps/${appId}/functions/${processorId}`);
  };

  const handleDeleteClick = (
    e: React.MouseEvent,
    processor: MessageProcessorListItem
  ) => {
    e.stopPropagation();
    setDeleteItem(processor);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.messageProcessorService.deleteMessageProcessor(
        deleteItem.id
      );
      notifySuccess("Function deleted successfully");
      queryClient.invalidateQueries({
        queryKey: getMessageProcessorsKey(appId || ""),
      });
      setDeleteItem(null);
    } catch (error) {
      console.error("Error deleting function:", error);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  return (
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-4">
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
                onClick={() => navigate(`/apps/${appId}/functions`)}
                className="hover:text-foreground cursor-pointer"
              >
                Functions
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">
            Functions
          </h1>
          <p className="animate-fade-in mt-2 text-gray-600">
            Manage and configure functions for {selectedApp?.app_name}
          </p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button onClick={handleCreateProcessor}>Create Function</Button>
        </div>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton
                key={index}
                showDescription
                metadataCount={1}
              />
            ))}
          </>
        ) : filteredProcessors.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No functions found"
              description="Get started by creating your first function"
              actionText="Create Function"
              onActionClick={handleCreateProcessor}
            />
          </div>
        ) : (
          <>
            {filteredProcessors.map((processor) => (
              <FunctionCard
                key={processor.id}
                processor={processor}
                onClick={handleProcessorClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Function"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Function Dialog */}
      {appId && (
        <CreateFunctionDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default FunctionsManagement;
