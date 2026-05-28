import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Checkbox } from '@app/components/ui/checkbox';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { IUser } from '@app/types/user';
import { App } from '@app/types/app';
import React, { useEffect, useState } from 'react';
import { useGetAllApps } from '@app/hooks';

interface ManageAppAccessDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  user: IUser | null;
  onSuccess?: () => void;
}

const ManageAppAccessDialog: React.FC<ManageAppAccessDialogProps> = ({ isOpen, onOpenChange, user, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const { data: allApps = [] } = useGetAllApps(true);

  const [userAppIds, setUserAppIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Fetch user's apps when dialog opens
  useEffect(() => {
    const fetchUserApps = async () => {
      if (!user || !isOpen) return;

      setLoading(true);
      try {
        const response = await floConsoleService.appUserService.listUserApps(user.id);
        setUserAppIds(response.data.data?.app_ids || []);
      } catch (error) {
        const errorMessage = extractErrorMessage(error);
        notifyError(errorMessage || 'Failed to load user apps');
      } finally {
        setLoading(false);
      }
    };

    fetchUserApps();
  }, [user, isOpen, notifyError]);

  const handleToggleApp = (appId: string, checked: boolean) => {
    if (checked) {
      setUserAppIds([...userAppIds, appId]);
    } else {
      setUserAppIds(userAppIds.filter((id) => id !== appId));
    }
  };

  const handleSave = async () => {
    if (!user) return;

    setSaving(true);
    try {
      // Get apps to grant and revoke
      const currentAppIds = new Set(userAppIds);
      const previousAppIds = new Set<string>();

      // Fetch current state again to compare
      const response = await floConsoleService.appUserService.listUserApps(user.id);
      response.data.data?.app_ids?.forEach((id) => previousAppIds.add(id));

      // Grant access to new apps
      const appsToGrant = Array.from(currentAppIds).filter((id) => !previousAppIds.has(id));
      for (const appId of appsToGrant) {
        await floConsoleService.appUserService.grantAppAccess(appId, user.id);
      }

      // Revoke access from removed apps
      const appsToRevoke = Array.from(previousAppIds).filter((id) => !currentAppIds.has(id));
      for (const appId of appsToRevoke) {
        await floConsoleService.appUserService.revokeAppAccess(appId, user.id);
      }

      notifySuccess('App access updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update app access');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Manage App Access</DialogTitle>
          <DialogDescription>Select which apps {user?.email} can access</DialogDescription>
        </DialogHeader>

        <div className="max-h-[400px] space-y-3 overflow-y-auto py-4">
          {loading ? (
            <div className="text-center text-gray-500">Loading apps...</div>
          ) : allApps.length === 0 ? (
            <div className="text-center text-gray-500">No apps available</div>
          ) : (
            allApps.map((app: App) => (
              <div key={app.id} className="flex items-center space-x-3 rounded p-2 hover:bg-gray-50">
                <Checkbox
                  id={`app-${app.id}`}
                  checked={userAppIds.includes(app.id)}
                  onCheckedChange={(checked) => handleToggleApp(app.id, checked as boolean)}
                />
                <label
                  htmlFor={`app-${app.id}`}
                  className="flex-1 cursor-pointer text-sm leading-none font-medium peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                >
                  {app.app_name}
                </label>
              </div>
            ))
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} loading={saving}>
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ManageAppAccessDialog;
