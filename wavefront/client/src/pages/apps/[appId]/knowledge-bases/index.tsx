import floConsoleService from "@app/api";
import { KbData } from "@app/api/knowledge-base-service";
import DeleteConfirmationDialog from "@app/components/DeleteConfirmationDialog";
import { EmptyStateCard } from "@app/components/EmptyCard";
import KnowledgeBaseCard from "@app/components/KnowledgeBaseCard";
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
import { useGetKnowledgeBases } from "@app/hooks";
import { getKnowledgeBasesKey } from "@app/hooks/data/query-keys";
import { useDashboardStore, useNotifyStore } from "@app/store";
import { useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router";
import CreateKnowledgeBaseDialog from "./CreateKnowledgeBaseDialog";

const KnowledgeBasesListPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const [searchTerm, setSearchTerm] = useState("");
  const [deleteItem, setDeleteItem] = useState<KbData | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch knowledge bases
  const { data: knowledgeBases = [], isLoading: loading } =
    useGetKnowledgeBases(appId);

  const handleDeleteClick = (e: React.MouseEvent, kb: KbData) => {
    e.stopPropagation();
    setDeleteItem(kb);
  };

  const handleDeleteConfirm = async () => {
    if (!appId || !deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.knowledgeBaseService.deleteKnowledgeBase(
        deleteItem.id
      );
      notifySuccess("Knowledge base deleted successfully");
      queryClient.invalidateQueries({ queryKey: getKnowledgeBasesKey(appId) });
      setDeleteItem(null);
    } catch (error) {
      console.error("Error deleting knowledge base:", error);
      let errorMessage = "Failed to delete knowledge base";

      if (error && typeof error === "object" && "response" in error) {
        const response = (error as any).response;
        if (response?.data?.meta?.error) {
          errorMessage = response.data.meta.error;
        } else if (response?.data?.message) {
          errorMessage = response.data.message;
        }
      }
      notifyError(errorMessage);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCardClick = (kbId: string) => {
    navigate(`/apps/${appId}/knowledge-bases/${kbId}`);
  };

  const handleCreateKnowledgeBase = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    if (!appId) return;
    queryClient.invalidateQueries({ queryKey: getKnowledgeBasesKey(appId) });
    setCreateDialogOpen(false);
  };

  const filteredKnowledgeBases = knowledgeBases.filter(
    (kb) =>
      kb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      kb.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

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
                onClick={() => navigate(`/apps/${appId}/knowledge-bases`)}
                className="hover:text-foreground cursor-pointer"
              >
                Knowledge Bases
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">
            Knowledge Bases
          </h1>
          <p className="animate-fade-in mt-2 text-gray-600">
            Manage knowledge bases for {selectedApp?.app_name}
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
          <Button onClick={handleCreateKnowledgeBase}>
            Create Knowledge Base
          </Button>
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
        ) : filteredKnowledgeBases.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No knowledge bases found"
              description="Get started by creating your first knowledge base"
              actionText="Create Knowledge Base"
              onActionClick={handleCreateKnowledgeBase}
            />
          </div>
        ) : (
          <>
            {filteredKnowledgeBases.map((kb) => (
              <KnowledgeBaseCard
                key={kb.id}
                kb={kb}
                onClick={handleCardClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Knowledge Base"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Knowledge Base Dialog */}
      {appId && (
        <CreateKnowledgeBaseDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default KnowledgeBasesListPage;
