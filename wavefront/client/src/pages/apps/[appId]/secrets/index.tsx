import ListHeader from '@app/components/ListHeader';
import ResourceCard, { ResourceCardSkeleton } from '@app/components/ResourceCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@app/components/ui/alert-dialog';
import { Button } from '@app/components/ui/button';
import { useDeleteConfirm, useDeleteSecret, useGetSecrets } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { Secret, SecretInUseData, secretRef } from '@app/types/secret';
import { matchesSearch } from '@app/utils/search';
import { isAxiosError } from 'axios';
import dayjs from 'dayjs';
import { KeyRound, RefreshCw } from 'lucide-react';
import React, { useState } from 'react';
import { Link, useParams } from 'react-router';
import SecretFormDialog, { SecretFormMode } from './SecretFormDialog';

type InUse = { secret: Secret; serviceIds: string[] };

/** The referencing services from a 409 on delete, or null for any other error. */
const referencingServices = (error: unknown): string[] | null => {
  if (!isAxiosError(error) || error.response?.status !== 409) return null;
  const data = (error.response.data as { data?: SecretInUseData } | undefined)?.data;
  return data?.service_ids ?? [];
};

const SecretsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const { selectedApp } = useDashboardStore();
  const { data: secrets = [], isLoading } = useGetSecrets(app);
  const deleteSecret = useDeleteSecret(app);

  const [searchQuery, setSearchQuery] = useState('');
  const [formMode, setFormMode] = useState<SecretFormMode>('create');
  const [formOpen, setFormOpen] = useState(false);
  const [formSecret, setFormSecret] = useState<Secret | null>(null);
  const [inUse, setInUse] = useState<InUse | null>(null);

  const deletion = useDeleteConfirm<Secret>(async (secret) => {
    try {
      await deleteSecret.mutateAsync(secret.id);
    } catch (error) {
      const serviceIds = referencingServices(error);
      if (serviceIds === null) throw error;
      // Close the confirmation and say which services still use it.
      setInUse({ secret, serviceIds });
    }
  });

  const openForm = (mode: SecretFormMode, secret: Secret | null) => {
    setFormMode(mode);
    setFormSecret(secret);
    setFormOpen(true);
  };

  const filteredSecrets = secrets.filter((secret) => matchesSearch(searchQuery, secret.name, secret.description));

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb className="shrink-0" items={[{ label: 'Secrets', to: `/apps/${app}/secrets` }]} />

      <ListHeader
        title="Secrets"
        count={filteredSecrets.length || undefined}
        subtitle={
          <>
            Credentials API services reference as {secretRef('NAME')} in {selectedApp?.app_name}
          </>
        }
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search secrets' }}
        primary={{ label: 'Create secret', onClick: () => openForm('create', null) }}
      />

      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, index) => (
            <ResourceCardSkeleton key={index} showDescription metadataCount={2} />
          ))
        ) : filteredSecrets.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No secrets found"
              description={
                searchQuery ? 'No secrets found matching your search.' : 'Create a secret to use it in an API service'
              }
              actionText="Create Secret"
              onActionClick={() => openForm('create', null)}
            />
          </div>
        ) : (
          filteredSecrets.map((secret) => (
            <ResourceCard
              key={secret.id}
              icon={KeyRound}
              title={secret.name}
              description={secret.description || undefined}
              metadata={[
                { label: 'Reference', value: secretRef(secret.name), isMono: true, isCopyable: true },
                ...(secret.updated_at
                  ? [{ label: 'Updated', value: dayjs(secret.updated_at).format('DD MMM YYYY') }]
                  : []),
              ]}
              onEditClick={() => openForm('edit', secret)}
              editTitle="Edit description"
              onDeleteClick={(e) => deletion.ask(secret, e)}
              deleteTitle="Delete secret"
              extraActions={[{ label: 'Rotate value', icon: RefreshCw, onClick: () => openForm('rotate', secret) }]}
            />
          ))
        )}
      </div>

      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Secret"
        message={`Are you sure you want to delete "${deletion.item?.name}"? This action cannot be undone.`}
      />

      <AlertDialog open={inUse !== null} onOpenChange={(open) => !open && setInUse(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Secret in use</AlertDialogTitle>
            <AlertDialogDescription>
              {inUse?.secret.name} can't be deleted while these API services reference it:
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="frost-text list-disc space-y-1 pl-5 text-sm">
            {inUse?.serviceIds.map((serviceId) => (
              <li key={serviceId}>
                <Link className="text-brand hover:underline" to={`/apps/${app}/api-services/${serviceId}`}>
                  {serviceId}
                </Link>
              </li>
            ))}
          </ul>
          <AlertDialogFooter>
            <Button type="button" variant="outline" onClick={() => setInUse(null)}>
              Close
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <SecretFormDialog isOpen={formOpen} onOpenChange={setFormOpen} mode={formMode} secret={formSecret} />
    </div>
  );
};

export default SecretsPage;
