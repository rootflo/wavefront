import floConsoleService from '@app/api';
import AppCard, { appCardShell } from '@app/components/AppCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Spinner } from '@app/components/ui/spinner';
import { useGetAllApps } from '@app/hooks';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { App } from '@app/types/app';
import { formatAppName } from '@app/lib/utils';
import { PlusIcon } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

const Dashboard: React.FC = () => {
  const [deleteItem, setDeleteItem] = useState<App | null>(null);
  const [deleting, setDeleting] = useState(false);

  const { data: apps = [], isLoading: appsLoading } = useGetAllApps(true);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess } = useNotifyStore();

  const { setSelectedApp } = useDashboardStore();

  const sortedApps = useMemo(
    () =>
      [...apps].sort((a, b) =>
        formatAppName(a.app_name).localeCompare(formatAppName(b.app_name), undefined, { sensitivity: 'base' })
      ),
    [apps]
  );

  const handleAppClick = (app: App) => {
    navigate(`/apps/${app.id}/agents`);
    setSelectedApp(app);
  };

  const handleCreateApp = () => {
    navigate('/apps/create');
  };

  const confirmDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      const deleteDeployment = deleteItem.deployment_type === 'auto';
      await floConsoleService.appService.deleteApp(deleteItem.id, deleteDeployment);
      notifySuccess(`App "${deleteItem.app_name}" deleted successfully`);

      queryClient.invalidateQueries({ queryKey: ['apps'] });

      setDeleteItem(null);
    } catch {
      setDeleteItem(null);
    } finally {
      setDeleting(false);
    }
  };

  const cancelDelete = () => {
    setDeleteItem(null);
  };

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(145deg,var(--frost-wash)_0%,#dbeafe_28%,#e0e7ff_58%,var(--frost-canvas)_100%)] dark:bg-[linear-gradient(145deg,#0b1220_0%,#0f172a_30%,#1e1b4b_62%,#0b1220_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgb(56_189_248_/_28%)_0%,rgb(99_102_241_/_18%)_28%,transparent_55%)] dark:bg-[radial-gradient(ellipse_at_center,rgb(56_189_248_/_14%)_0%,rgb(99_102_241_/_12%)_28%,transparent_55%)]" />
        <div className="absolute top-1/2 left-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-300/35 blur-3xl dark:bg-sky-500/18" />
        <div className="absolute top-0 left-0 h-80 w-80 -translate-x-1/4 -translate-y-1/4 rounded-full bg-sky-400/35 blur-3xl dark:bg-sky-500/20" />
        <div className="absolute top-1/3 right-0 h-72 w-72 translate-x-1/4 rounded-full bg-indigo-400/30 blur-3xl dark:bg-indigo-500/18" />
        <div className="absolute bottom-0 left-1/2 h-72 w-72 -translate-x-1/2 translate-y-1/4 rounded-full bg-cyan-300/30 blur-3xl dark:bg-cyan-500/15" />
      </div>

      <div className="animate-fade-in relative mx-auto flex h-full w-full max-w-7xl flex-col gap-8 px-8 pt-10 pb-6 md:px-12 lg:px-16">
        <div className="flex shrink-0 flex-col items-center justify-center gap-5 text-center">
          <p className="frost-text max-w-2xl text-3xl font-semibold md:text-[40px]">
            Welcome to Rootflo's App Management Dashboard
          </p>
          <p className="frost-text-muted max-w-xl text-base font-normal md:text-[20px]">
            Manage configurations across different applications
          </p>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <p className="frost-text-muted shrink-0 text-base font-medium">Your applications</p>
          <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto pb-2">
            <div className="grid w-full grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              <div className={`${appCardShell} items-center justify-center gap-2`} onClick={handleCreateApp}>
                <PlusIcon className="frost-text relative h-4 w-4" />
                <p className="frost-text relative text-center text-[13px] font-medium tracking-normal normal-case">
                  Create new application
                </p>
              </div>
              {appsLoading ? (
                <div className="col-span-full flex w-full items-center justify-center">
                  <Spinner />
                </div>
              ) : (
                sortedApps.map((app) => (
                  <AppCard
                    key={app.id}
                    app={app}
                    onClick={handleAppClick}
                    onDeleteClick={(app) => setDeleteItem(app)}
                  />
                ))
              )}
            </div>
          </div>
        </div>

        <DeleteConfirmationDialog
          isOpen={!!deleteItem}
          title="Delete Application"
          message={`Are you sure you want to delete "${deleteItem?.app_name}"? This action cannot be undone and will remove all associated data.`}
          onConfirm={confirmDelete}
          onCancel={cancelDelete}
          loading={deleting}
        />
      </div>
    </div>
  );
};

export default Dashboard;
