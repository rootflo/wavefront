import ListHeader from '@app/components/ListHeader';
import { KbData } from '@app/api/knowledge-base-service';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import KnowledgeBaseCard from '@app/components/KnowledgeBaseCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteKnowledgeBase, useGetKnowledgeBases } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import KnowledgeBaseFormDialog from './KnowledgeBaseFormDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const KnowledgeBasesListPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const deleteKnowledgeBase = useDeleteKnowledgeBase(appId);
  const deletion = useDeleteConfirm<KbData>((item) => deleteKnowledgeBase.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<KbData | null>(null);

  // Fetch knowledge bases
  const { data: knowledgeBases = [], isLoading: loading } = useGetKnowledgeBases(appId);

  const handleEditClick = (e: React.MouseEvent, kb: KbData) => {
    e.stopPropagation();
    setEditItem(kb);
  };

  const handleCardClick = (kbId: string) => {
    navigate(`/apps/${appId}/knowledge-bases/${kbId}`);
  };

  const handleCreateKnowledgeBase = () => {
    setCreateDialogOpen(true);
  };

  const filteredKnowledgeBases = knowledgeBases.filter((kb) => matchesSearch(searchTerm, kb.name, kb.id));

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Knowledge Bases', to: `/apps/${appId}/knowledge-bases` }]} />

      <ListHeader
        title="Knowledge Bases"
        count={filteredKnowledgeBases.length || undefined}
        subtitle={<>Manage knowledge bases for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search knowledge bases' }}
        primary={{ label: 'Create knowledge base', onClick: handleCreateKnowledgeBase }}
      />
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={1} />
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
                onDeleteClick={(e, item) => deletion.ask(item, e)}
                onEditClick={handleEditClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Knowledge Base"
        message={`Are you sure you want to delete "${deletion.item?.name}"? This action cannot be undone.`}
      />

      {/* Create Knowledge Base Dialog */}
      {appId && <KnowledgeBaseFormDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={appId} />}

      {/* Edit Knowledge Base Dialog */}
      {appId && editItem && (
        <KnowledgeBaseFormDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          appId={appId}
          knowledgeBase={editItem}
        />
      )}
    </div>
  );
};

export default KnowledgeBasesListPage;
