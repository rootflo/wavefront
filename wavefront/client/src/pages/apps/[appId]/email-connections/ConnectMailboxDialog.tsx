import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
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
import { EMAIL_CAPABILITIES, getEmailProviderOptions } from '@app/config/email-providers';
import { useGetOAuthApps } from '@app/hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { EmailCapability, EmailProviderType } from '@app/types/email';
import React, { useEffect, useMemo, useState } from 'react';

interface ConnectMailboxDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const ConnectMailboxDialog: React.FC<ConnectMailboxDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const { notifyError } = useNotifyStore();
  const { data: oauthApps = [] } = useGetOAuthApps(appId);

  const [name, setName] = useState('');
  const [provider, setProvider] = useState<EmailProviderType>('gmail');
  const [oauthAppId, setOauthAppId] = useState<string>('');
  const [capabilities, setCapabilities] = useState<EmailCapability[]>(['read']);
  const [loading, setLoading] = useState(false);

  const eligibleApps = useMemo(
    () => oauthApps.filter((oauthApp) => oauthApp.provider === provider && oauthApp.is_enabled),
    [oauthApps, provider]
  );

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setProvider('gmail');
    setOauthAppId('');
    setCapabilities(['read']);
  }, [isOpen]);

  // With exactly one enabled app for the provider, preselect it.
  useEffect(() => {
    setOauthAppId(eligibleApps.length === 1 ? eligibleApps[0].id : '');
  }, [eligibleApps]);

  const toggleCapability = (capability: EmailCapability) => {
    setCapabilities((prev) =>
      prev.includes(capability) ? prev.filter((c) => c !== capability) : [...prev, capability]
    );
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      notifyError('Name is required');
      return;
    }
    if (!oauthAppId) {
      notifyError('Select an OAuth app');
      return;
    }
    if (capabilities.length === 0) {
      notifyError('Select at least one capability');
      return;
    }

    setLoading(true);
    try {
      const emailsPageUrl = `${window.location.origin}/apps/${appId}/email-connections`;
      const response = await floConsoleService.emailConnectionService.createEmailConnection({
        name: name.trim(),
        provider,
        oauth_app_id: oauthAppId,
        capabilities,
        success_redirect_url: emailsPageUrl,
        failure_redirect_url: emailsPageUrl,
      });

      const authorizationUrl = response.data?.data?.authorization_url;
      if (!authorizationUrl) {
        notifyError('Connection created but no consent URL was returned');
        return;
      }

      onSuccess?.();
      onOpenChange(false);
      // The mailbox owner has to grant consent on the provider's own domain, so
      // the flow leaves the app here and comes back through the OAuth callback.
      window.location.assign(authorizationUrl);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to start connecting the mailbox');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Connect a Mailbox</DialogTitle>
          <DialogDescription>
            You will be sent to the provider to grant access, then returned here once consent is given.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div>
            <label className="frost-text mb-1 block text-sm font-medium">
              Name<span className="text-red-500">*</span>
            </label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Support inbox" maxLength={255} />
          </div>

          <div>
            <label className="frost-text mb-1 block text-sm font-medium">
              Provider<span className="text-red-500">*</span>
            </label>
            <Select value={provider} onValueChange={(value) => setProvider(value as EmailProviderType)}>
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

          <div>
            <label className="frost-text mb-1 block text-sm font-medium">
              OAuth app<span className="text-red-500">*</span>
            </label>
            {eligibleApps.length === 0 ? (
              <p className="text-xs text-red-600">
                No enabled OAuth app for this provider. Register one under OAuth Apps first.
              </p>
            ) : (
              <Select value={oauthAppId} onValueChange={setOauthAppId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an OAuth app" />
                </SelectTrigger>
                <SelectContent>
                  {eligibleApps.map((oauthApp) => (
                    <SelectItem key={oauthApp.id} value={oauthApp.id}>
                      {oauthApp.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div>
            <p className="frost-text mb-2 text-sm font-medium">
              Capabilities<span className="text-red-500">*</span>
            </p>
            <div className="space-y-3">
              {EMAIL_CAPABILITIES.map((capability) => (
                <div key={capability.value} className="flex items-start gap-3">
                  <Checkbox
                    checked={capabilities.includes(capability.value)}
                    onCheckedChange={() => toggleCapability(capability.value)}
                  />
                  <div>
                    <label className="frost-text text-sm font-medium">{capability.label}</label>
                    <p className="frost-text-muted text-xs">{capability.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" loading={loading} disabled={eligibleApps.length === 0} onClick={handleSubmit}>
            Continue to Consent
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ConnectMailboxDialog;
