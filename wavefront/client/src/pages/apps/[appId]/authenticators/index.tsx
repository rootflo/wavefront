import ListHeader from '@app/components/ListHeader';
import AuthenticatorCard from '@app/components/AuthenticatorCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteAuthenticator, useGetAuthenticators } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { Authenticator } from '@app/types/authenticator';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateAuthenticatorDialog from './CreateAuthenticatorDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const AuthenticatorsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const deleteAuthenticator = useDeleteAuthenticator(app);
  const deletion = useDeleteConfirm<Authenticator>((item) => deleteAuthenticator.mutateAsync(item.auth_id));
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch authenticators
  const { data: authenticators = [], isLoading: authenticatorsLoading } = useGetAuthenticators(app);

  const handleCreateAuthenticator = () => {
    setCreateDialogOpen(true);
  };

  // Filter authenticators based on search
  const filteredAuthenticators = authenticators.filter((authenticator) =>
    matchesSearch(searchQuery, authenticator.auth_name, authenticator.auth_desc, authenticator.auth_type)
  );

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Authenticators', to: `/apps/${app}/authenticators` }]} />

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
                onDeleteClick={(e, item) => deletion.ask(item, e)}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Authenticator"
        message={`Are you sure you want to delete "${deletion.item?.auth_name}"? This action cannot be undone.`}
      />

      {/* Create Authenticator Dialog */}
      {app && <CreateAuthenticatorDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={app} />}
    </div>
  );
};

export default AuthenticatorsPage;
