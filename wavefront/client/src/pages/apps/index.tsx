import floConsoleService from '@app/api';
import AppCard from '@app/components/AppCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Spinner } from '@app/components/ui/spinner';
import { useGetAllApps } from '@app/hooks';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { App } from '@app/types/app';
import { PlusIcon } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate } from 'react-router';

const Dashboard: React.FC = () => {
  const [deleteItem, setDeleteItem] = useState<App | null>(null);
  const [deleting, setDeleting] = useState(false);

  const { data: apps = [], isLoading: appsLoading } = useGetAllApps(true);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess } = useNotifyStore();

  const { setSelectedApp } = useDashboardStore();

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
      await floConsoleService.appService.deleteApp(deleteItem.id);
      notifySuccess(`App "${deleteItem.app_name}" deleted successfully`);

      // Refresh the apps list
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
    <div className="animate-fade-in flex h-full w-full flex-col items-center gap-[60px] overflow-y-auto bg-[url('/background.webp')] bg-cover bg-center px-[152px] pt-[64px] pb-10">
      <div className="flex flex-col items-center justify-center gap-5">
        <div className="flex w-[626px] items-center justify-center text-center">
          <p className="text-[40px] font-semibold text-[#101010]">Welcome to Rootflo's App Management Dashboard</p>
        </div>
        <p className="text-[20px] font-normal text-[#404040]">Manage configurations across different applications</p>
      </div>
      <div className="flex w-full flex-col items-center justify-center gap-8">
        <p className="text-base font-medium text-[#404040]">Your applications</p>
        <div className="grid w-full justify-center gap-5 xl:grid-cols-2 2xl:grid-cols-3">
          <div
            className="flex w-full cursor-pointer flex-col items-center justify-center gap-8 rounded-xl border border-[#FFF] bg-white/60 p-5"
            onClick={handleCreateApp}
          >
            <PlusIcon className="h-6 w-6 text-[#101010]" />
            <p className="text-lg font-medium text-[#101010]">Create new application</p>
          </div>
          {appsLoading ? (
            <div className="flex w-full items-center justify-center">
              <Spinner />
            </div>
          ) : (
            apps.map((app) => (
              <AppCard key={app.id} app={app} onClick={handleAppClick} onDeleteClick={(app) => setDeleteItem(app)} />
            ))
          )}
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
  );
};

export default Dashboard;
