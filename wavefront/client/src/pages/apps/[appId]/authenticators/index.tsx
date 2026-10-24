import ListHeader from '@app/components/ListHeader';
import floConsoleService from '@app/api';
import AuthenticatorCard from '@app/components/AuthenticatorCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { useGetAuthenticators } from '@app/hooks';
import { getAuthenticatorsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { Authenticator } from '@app/types/authenticator';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateAuthenticatorDialog from './CreateAuthenticatorDialog';

const AuthenticatorsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<Authenticator | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch authenticators
  const { data: authenticators = [], isLoading: authenticatorsLoading } = useGetAuthenticators(app);

  const handleDeleteClick = (e: React.MouseEvent, authenticator: Authenticator) => {
    e.stopPropagation();
    setDeleteItem(authenticator);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem || !app) return;

    setDeleting(true);
    try {
      await floConsoleService.authenticatorService.deleteAuthenticator(deleteItem.auth_id);
      notifySuccess('Authenticator deleted successfully');
      queryClient.invalidateQueries({ queryKey: getAuthenticatorsKey(app) });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete authenticator');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateAuthenticator = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getAuthenticatorsKey(app || '') });
    setCreateDialogOpen(false);
  };

  // Filter authenticators based on search
  const filteredAuthenticators = authenticators.filter((authenticator) => {
    const query = searchQuery.toLowerCase();
    return (
      authenticator.auth_name.toLowerCase().includes(query) ||
      (authenticator.auth_desc && authenticator.auth_desc.toLowerCase().includes(query)) ||
      authenticator.auth_type.toLowerCase().includes(query)
    );
  });

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <Breadcrumb className="mb-4 hidden md:block">
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
                onClick={() => navigate(`/apps/${app}/authenticators`)}
                className="hover:text-foreground cursor-pointer"
              >
                Authenticators
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <ListHeader
        title="Authenticators"
        count={filteredAuthenticators.length || undefined}
        subtitle={<>Manage authentication provider configurations for {selectedApp?.app_name}</>}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search authenticators' }}
        primary={{ label: 'Create authenticator', onClick: handleCreateAuthenticator }}
      />
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {authenticatorsLoading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={2} />
            ))}
          </>
        ) : filteredAuthenticators.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No authenticators found"
              description={
                searchQuery
                  ? 'No authenticators found matching your search.'
                  : 'Get started by creating your first authenticator'
              }
              actionText="Create Authenticator"
              onActionClick={handleCreateAuthenticator}
            />
          </div>
        ) : (
          <>
            {filteredAuthenticators.map((authenticator) => (
              <AuthenticatorCard
                key={authenticator.auth_id}
                authenticator={authenticator}
                onClick={(authId) => navigate(`/apps/${app}/authenticators/${authId}`)}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Authenticator"
        message={`Are you sure you want to delete "${deleteItem?.auth_name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Authenticator Dialog */}
      {app && (
        <CreateAuthenticatorDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={app}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default AuthenticatorsPage;
