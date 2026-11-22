import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { useCreateSecret, useUpdateSecret } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { SECRET_NAME_PATTERN, Secret, secretRef } from '@app/types/secret';
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router';

/** create: name, value, description. rotate: a new value only. edit: the description only. */
export type SecretFormMode = 'create' | 'rotate' | 'edit';

interface SecretFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  mode: SecretFormMode;
  /** The secret being rotated or edited; null when creating. */
  secret?: Secret | null;
}

const TITLES: Record<SecretFormMode, string> = {
  create: 'Create Secret',
  rotate: 'Rotate Secret Value',
  edit: 'Edit Secret',
};

const SecretFormDialog: React.FC<SecretFormDialogProps> = ({ isOpen, onOpenChange, mode, secret = null }) => {
  const { app } = useParams<{ app: string }>();
  const { notifyError } = useNotifyStore();
  const createSecret = useCreateSecret(app);
  const updateSecret = useUpdateSecret(app);

  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    // The value is write-only, so it always starts blank.
    setName(secret?.name ?? '');
    setValue('');
    setDescription(secret?.description ?? '');
  }, [isOpen, secret]);

  const nameError =
    mode === 'create' && name && !SECRET_NAME_PATTERN.test(name) ? 'Use UPPER_SNAKE_CASE, e.g. ACME_API_TOKEN' : '';

  const handleSubmit = () => {
    const close = () => onOpenChange(false);

    if (mode === 'create') {
      if (!SECRET_NAME_PATTERN.test(name)) {
        notifyError('Name must be UPPER_SNAKE_CASE');
        return;
      }
      if (!value) {
        notifyError('Value is required');
        return;
      }
      createSecret.mutate({ name, value, description: description.trim() || null }, { onSuccess: close });
      return;
    }

    if (!secret) return;
    if (mode === 'rotate') {
      if (!value) {
        notifyError('Value is required');
        return;
      }
      updateSecret.mutate({ secretId: secret.id, data: { value } }, { onSuccess: close });
      return;
    }
    updateSecret.mutate({ secretId: secret.id, data: { description: description.trim() } }, { onSuccess: close });
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{TITLES[mode]}</DialogTitle>
          <DialogDescription>
            {mode === 'rotate'
              ? 'API services that use this secret pick up the new value automatically.'
              : `Reference it in an API service as ${secretRef(name || 'NAME')}. The value can't be viewed once saved.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div>
            <label className="frost-text mb-1 block text-sm font-medium">
              Name{mode === 'create' && <span className="text-red-500">*</span>}
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value.toUpperCase())}
              placeholder="ACME_API_TOKEN"
              maxLength={128}
              disabled={mode !== 'create'}
              autoComplete="off"
            />
            {nameError && <p className="mt-1 text-xs text-red-500">{nameError}</p>}
          </div>

          {mode !== 'edit' && (
            <div>
              <label className="frost-text mb-1 block text-sm font-medium">
                {mode === 'rotate' ? 'New value' : 'Value'}
                <span className="text-red-500">*</span>
              </label>
              <Input
                type="password"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={mode === 'rotate' ? 'Replaces the stored value' : 'Secret value'}
                autoComplete="new-password"
              />
            </div>
          )}

          {mode !== 'rotate' && (
            <div>
              <label className="frost-text mb-1 block text-sm font-medium">Description</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                maxLength={255}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            loading={createSecret.isPending || updateSecret.isPending}
            disabled={!!nameError}
            onClick={handleSubmit}
          >
            {mode === 'create' ? 'Create Secret' : mode === 'rotate' ? 'Rotate Value' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SecretFormDialog;
