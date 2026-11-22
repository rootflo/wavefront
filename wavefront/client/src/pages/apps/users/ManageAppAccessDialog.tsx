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
import { formatAppName } from '@app/utils/string-formatting';
import { IUser } from '@app/types/user';
import { App } from '@app/types/app';
import React, { useEffect, useState } from 'react';
import { useGetAllApps, useGetUserApps, useUpdateUserAppAccess } from '@app/hooks';

interface ManageAppAccessDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  user: IUser | null;
}

const ManageAppAccessDialog: React.FC<ManageAppAccessDialogProps> = ({ isOpen, onOpenChange, user }) => {
  const { data: allApps = [] } = useGetAllApps(true);

  const { data: savedAppIds, isLoading: loading } = useGetUserApps(user?.id, isOpen);
  const [userAppIds, setUserAppIds] = useState<string[]>([]);
  const updateAccess = useUpdateUserAppAccess();

  // The checkboxes start from the user's saved access each time the dialog opens
  useEffect(() => {
    if (isOpen && savedAppIds) setUserAppIds(savedAppIds);
  }, [isOpen, savedAppIds]);

  const handleToggleApp = (appId: string, checked: boolean) => {
    if (checked) {
      setUserAppIds([...userAppIds, appId]);
    } else {
      setUserAppIds(userAppIds.filter((id) => id !== appId));
    }
  };

  const handleSave = () => {
    if (!user) return;
    updateAccess.mutate({ userId: user.id, appIds: userAppIds }, { onSuccess: () => onOpenChange(false) });
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
            <div className="frost-text-muted text-center">Loading apps...</div>
          ) : allApps.length === 0 ? (
            <div className="frost-text-muted text-center">No apps available</div>
          ) : (
            allApps.map((app: App) => (
              <div key={app.id} className="hover:bg-frost-glass-strong flex items-center space-x-3 rounded p-2">
                <Checkbox
                  id={`app-${app.id}`}
                  checked={userAppIds.includes(app.id)}
                  onCheckedChange={(checked) => handleToggleApp(app.id, checked as boolean)}
                />
                <label
                  htmlFor={`app-${app.id}`}
                  className="flex-1 cursor-pointer text-sm leading-none font-medium peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                >
                  {formatAppName(app.app_name)}
                </label>
              </div>
            ))
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} loading={updateAccess.isPending}>
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ManageAppAccessDialog;
