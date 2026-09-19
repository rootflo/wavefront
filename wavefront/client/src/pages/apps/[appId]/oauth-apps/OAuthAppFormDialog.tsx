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
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import {
  cleanEmailProviderParameters,
  getEmailProviderConfig,
  getEmailProviderOptions,
  initializeEmailProviderParameters,
  missingEmailProviderFields,
} from '@app/config/email-providers';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { EmailProviderType } from '@app/types/email';
import { OAuthApp } from '@app/types/oauth-app';
import React, { useEffect, useState } from 'react';

interface OAuthAppFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** The app being edited, or null to create a new one. */
  oauthApp?: OAuthApp | null;
  onSuccess?: () => void;
}

const humanize = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const OAuthAppFormDialog: React.FC<OAuthAppFormDialogProps> = ({
  isOpen,
  onOpenChange,
  oauthApp = null,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const isEdit = !!oauthApp;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [provider, setProvider] = useState<EmailProviderType>('gmail');
  const [parameters, setParameters] = useState<Record<string, unknown>>(() =>
    initializeEmailProviderParameters('gmail')
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    if (oauthApp) {
      setName(oauthApp.name);
      setDescription(oauthApp.description || '');
      setProvider(oauthApp.provider);
      // The client secret is never returned, so it starts blank and is only sent
      // when the admin types a replacement.
      setParameters({
        ...initializeEmailProviderParameters(oauthApp.provider),
        ...(oauthApp.config || {}),
        client_secret: '',
      });
    } else {
      setName('');
      setDescription('');
      setProvider('gmail');
      setParameters(initializeEmailProviderParameters('gmail'));
    }
  }, [isOpen, oauthApp]);

  const handleProviderChange = (value: string) => {
    const next = value as EmailProviderType;
    setProvider(next);
    setParameters(initializeEmailProviderParameters(next));
  };

  const setParameter = (key: string, value: unknown) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      notifyError('Name is required');
      return;
    }
    if (/\s/.test(name.trim())) {
      notifyError('Name cannot contain spaces');
      return;
    }

    const config = cleanEmailProviderParameters(parameters);
    // On edit an omitted secret keeps the stored one, so it is only required
    // when there is nothing stored yet.
    const skipSecretCheck = isEdit && oauthApp?.has_client_secret;
    const missing = missingEmailProviderFields(provider, config).filter(
      (field) => !(skipSecretCheck && field === 'client_secret')
    );
    if (missing.length > 0) {
      notifyError(`Missing required fields: ${missing.map(humanize).join(', ')}`);
      return;
    }

    setLoading(true);
    try {
      if (isEdit && oauthApp) {
        await floConsoleService.oauthAppService.updateOAuthApp(oauthApp.id, {
          name: name.trim(),
          description: description.trim() || null,
          config,
        });
        notifySuccess('OAuth app updated successfully');
      } else {
        await floConsoleService.oauthAppService.createOAuthApp({
          name: name.trim(),
          provider,
          description: description.trim() || null,
          config,
        });
        notifySuccess('OAuth app created successfully');
      }
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      notifyError(extractErrorMessage(error) || `Failed to ${isEdit ? 'update' : 'create'} OAuth app`);
    } finally {
      setLoading(false);
    }
  };

  const config = getEmailProviderConfig(provider);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit OAuth App' : 'Register OAuth App'}</DialogTitle>
          <DialogDescription>
            The OAuth application mailboxes connect through for {selectedApp?.app_name}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="frost-text mb-1 block text-sm font-medium">
                Name<span className="text-red-500">*</span>
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="gmail-primary"
                maxLength={64}
              />
            </div>

            <div>
              <label className="frost-text mb-1 block text-sm font-medium">
                Provider<span className="text-red-500">*</span>
              </label>
              <Select value={provider} onValueChange={handleProviderChange} disabled={isEdit}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a provider" />
                </SelectTrigger>
                <SelectContent>
                  {getEmailProviderOptions().map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <label className="frost-text mb-1 block text-sm font-medium">Description</label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              maxLength={255}
            />
          </div>

          {config && (
            <div className="frost-glass border-frost-border ring-frost-border space-y-4 rounded-lg border p-6 ring-1">
              <h3 className="frost-text text-lg font-semibold">Configuration</h3>
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(config.parameters).map(([key, paramConfig]) => (
                  <div key={key}>
                    <label className="frost-text mb-1 block text-sm font-medium">
                      {humanize(key)}
                      {paramConfig.required && <span className="text-red-500">*</span>}
                    </label>
                    <Input
                      type={key === 'client_secret' ? 'password' : 'text'}
                      value={String(parameters[key] ?? '')}
                      onChange={(e) => setParameter(key, e.target.value)}
                      placeholder={
                        key === 'client_secret' && isEdit && oauthApp?.has_client_secret
                          ? 'Leave blank to keep the stored secret'
                          : paramConfig.placeholder
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" loading={loading} onClick={handleSubmit}>
            {isEdit ? 'Save Changes' : 'Register App'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default OAuthAppFormDialog;
