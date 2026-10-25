import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import DetailActions from '@app/components/DetailActions';
import MobileBackButton from '@app/components/MobileBackButton';
import PageTitle from '@app/components/PageTitle';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import {
  cleanParameters,
  getProviderBadge,
  getProviderConfig,
  mergeParameters,
  ParameterConfig,
} from '@app/config/authenticators';
import { useGetAuthenticator } from '@app/hooks/data/fetch-hooks';
import { copyToClipboard, formatAppName } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import {
  getBooleanNestedParameter,
  getBooleanParameter,
  getNumberOrStringNestedParameter,
  getNumberOrStringParameter,
  getStringNestedParameter,
  getStringParameter,
} from '@app/utils/parameter-helpers';
import { Copy } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useDeleteAuthenticator, useSetAuthenticatorEnabled, useUpdateAuthenticator } from '@app/hooks';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const formatFieldName = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const fieldId = (...parts: string[]) => ['authenticator', ...parts].join('-');

const AuthenticatorDetailPage: React.FC = () => {
  const { app, authId } = useParams<{ app: string; authId: string }>();
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const updateAuthenticator = useUpdateAuthenticator(app);
  const deleteAuthenticator = useDeleteAuthenticator(app);
  const setAuthenticatorEnabled = useSetAuthenticatorEnabled(app);

  const [authDesc, setAuthDesc] = useState('');
  const [parameters, setParameters] = useState<Record<string, unknown>>({});

  const { data: authenticator, isLoading: authenticatorLoading } = useGetAuthenticator(app, authId);

  useEffect(() => {
    if (authenticator) {
      setAuthDesc(authenticator.auth_desc || '');
      setParameters(mergeParameters(authenticator.auth_type, authenticator.config));
    }
  }, [authenticator]);

  const setParameter = (key: string, value: unknown) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setNestedParameter = (parentKey: string, childKey: string, value: unknown) => {
    setParameters((prev) => {
      const parentValue = prev[parentKey];
      const isObject = typeof parentValue === 'object' && parentValue !== null && !Array.isArray(parentValue);
      return {
        ...prev,
        [parentKey]: {
          ...(isObject ? (parentValue as Record<string, unknown>) : {}),
          [childKey]: value,
        },
      };
    });
  };

  const handleCancel = () => {
    if (authenticator) {
      setAuthDesc(authenticator.auth_desc || '');
      setParameters(mergeParameters(authenticator.auth_type, authenticator.config));
    }
    setIsEditing(false);
  };

  const handleSave = () => {
    if (!authId) return;
    updateAuthenticator.mutate(
      { authId, data: { auth_desc: authDesc.trim() || null, config: cleanParameters(parameters) } },
      { onSuccess: () => setIsEditing(false) }
    );
  };

  const handleDelete = () => {
    if (!authId) return;
    deleteAuthenticator.mutate(authId, { onSuccess: () => navigate(`/apps/${app}/authenticators`) });
  };

  const handleToggleEnabled = (enabled: boolean) => {
    if (!authId || !authenticator) return;
    setAuthenticatorEnabled.mutate({ authId, enabled });
  };

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const renderParameterField = (key: string, disabled: boolean) => {
    if (!authenticator) return null;

    const config = getProviderConfig(authenticator.auth_type);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    if (paramConfig.type === 'object' && paramConfig.fields) {
      return (
        <div className="frost-panel ring-frost-border col-span-full space-y-4 rounded-xl border p-4 ring-1">
          <Label>{formatFieldName(key)}</Label>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {Object.entries(paramConfig.fields).map(([nestedKey, nestedConfig]) => (
              <div key={nestedKey} className="flex flex-col gap-2">
                <Label htmlFor={fieldId('param', key, nestedKey)} className="text-xs">
                  {formatFieldName(nestedKey)}
                </Label>
                {renderNestedField(key, nestedKey, nestedConfig, disabled)}
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (paramConfig.type === 'array') {
      const arrayValue = Array.isArray(parameters[key]) ? parameters[key].join(', ') : '';
      return (
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId('param', key)}>{formatFieldName(key)}</Label>
          <Input
            id={fieldId('param', key)}
            value={arrayValue}
            onChange={(e) => {
              const values = e.target.value
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean);
              setParameter(key, values);
            }}
            disabled={disabled}
            placeholder={paramConfig.placeholder}
          />
        </div>
      );
    }

    if (paramConfig.type === 'boolean') {
      return (
        <div className="flex items-start gap-3">
          <Checkbox
            id={fieldId('param', key)}
            checked={getBooleanParameter(parameters, key)}
            onCheckedChange={(checked) => setParameter(key, checked === true)}
            disabled={disabled}
          />
          <div>
            <Label htmlFor={fieldId('param', key)}>{formatFieldName(key)}</Label>
          </div>
        </div>
      );
    }

    if (paramConfig.type === 'number') {
      return (
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId('param', key)}>{formatFieldName(key)}</Label>
          <Input
            id={fieldId('param', key)}
            type="number"
            value={getNumberOrStringParameter(parameters, key)}
            onChange={(e) => setParameter(key, e.target.value ? Number(e.target.value) : '')}
            disabled={disabled}
            min={paramConfig.min}
            max={paramConfig.max}
            step={paramConfig.step}
            placeholder={paramConfig.placeholder}
          />
        </div>
      );
    }

    if (paramConfig.type === 'select' && paramConfig.options) {
      return (
        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId('param', key)}>{formatFieldName(key)}</Label>
          <Select
            value={getStringParameter(parameters, key)}
            onValueChange={(value) => setParameter(key, value)}
            disabled={disabled}
          >
            <SelectTrigger id={fieldId('param', key)}>
              <SelectValue placeholder="Select an option" />
            </SelectTrigger>
            <SelectContent>
              {paramConfig.options.map((option) => (
                <SelectItem key={String(option.value)} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      );
    }

    return (
      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId('param', key)}>{formatFieldName(key)}</Label>
        <Input
          id={fieldId('param', key)}
          type="text"
          value={getStringParameter(parameters, key)}
          onChange={(e) => setParameter(key, e.target.value)}
          disabled={disabled}
          placeholder={paramConfig.placeholder}
        />
      </div>
    );
  };

  const renderNestedField = (parentKey: string, childKey: string, config: ParameterConfig, disabled: boolean) => {
    const id = fieldId('param', parentKey, childKey);

    if (config.type === 'boolean') {
      return (
        <Checkbox
          id={id}
          checked={getBooleanNestedParameter(parameters, parentKey, childKey)}
          onCheckedChange={(checked) => setNestedParameter(parentKey, childKey, checked === true)}
          disabled={disabled}
        />
      );
    }

    if (config.type === 'number') {
      return (
        <Input
          id={id}
          type="number"
          value={getNumberOrStringNestedParameter(parameters, parentKey, childKey)}
          onChange={(e) => setNestedParameter(parentKey, childKey, e.target.value ? Number(e.target.value) : '')}
          disabled={disabled}
          min={config.min}
          max={config.max}
          step={config.step}
        />
      );
    }

    return (
      <Input
        id={id}
        type="text"
        value={getStringNestedParameter(parameters, parentKey, childKey)}
        onChange={(e) => setNestedParameter(parentKey, childKey, e.target.value)}
        disabled={disabled}
        placeholder={config.placeholder}
      />
    );
  };

  const config = authenticator ? getProviderConfig(authenticator.auth_type) : null;
  const badge = authenticator ? getProviderBadge(authenticator.auth_type) : null;

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb
        items={[
          { label: 'Authenticators', to: `/apps/${app}/authenticators` },
          { label: authenticator?.auth_name || authId, loading: authenticatorLoading },
        ]}
      />

      {authenticatorLoading ? (
        <>
          <div className="mb-6 flex min-w-0 items-center gap-2 sm:mb-8">
            <MobileBackButton to={`/apps/${app}/authenticators`} label="Back to authenticators" />
            <PageTitle loading />
          </div>
          <p className="frost-text-muted text-sm">Loading authenticator...</p>
        </>
      ) : !authenticator ? (
        <p className="text-sm text-red-500">Authenticator not found</p>
      ) : (
        <>
          <div className="mb-6 flex w-full items-start justify-between gap-3 sm:mb-8">
            <div className="flex min-w-0 flex-1 flex-col gap-2 sm:gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <MobileBackButton to={`/apps/${app}/authenticators`} label="Back to authenticators" />
                <PageTitle>{formatAppName(authenticator.auth_name)}</PageTitle>
              </div>
              <div className="flex flex-wrap items-center gap-3 max-md:pl-1">
                {badge && (
                  <Badge variant="secondary" className={`${badge.bg} ${badge.text} border-0 font-normal`}>
                    {config?.name || authenticator.auth_type}
                  </Badge>
                )}
                <label className="frost-text-muted flex items-center gap-2 text-xs">
                  <Switch
                    checked={authenticator.is_enabled}
                    onCheckedChange={(checked) => void handleToggleEnabled(checked)}
                    disabled={setAuthenticatorEnabled.isPending}
                    title={authenticator.is_enabled ? 'Enabled' : 'Disabled'}
                  />
                  {authenticator.is_enabled ? 'Enabled' : 'Disabled'}
                </label>
              </div>
            </div>
            <DetailActions
              editing={isEditing}
              onEdit={() => setIsEditing(true)}
              onDelete={() => setShowDeleteModal(true)}
              onSave={() => void handleSave()}
              onCancel={handleCancel}
              saving={updateAuthenticator.isPending}
            />
          </div>

          <div className="grid w-full grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={fieldId('description')}>Description</Label>
                <Textarea
                  id={fieldId('description')}
                  value={authDesc}
                  onChange={(e) => setAuthDesc(e.target.value)}
                  disabled={!isEditing}
                  rows={3}
                  maxLength={500}
                  placeholder="Optional description for this authenticator"
                />
                {isEditing && <p className="frost-text-muted text-xs">{authDesc.length}/500 characters</p>}
              </div>

              {config && (
                <div className="frost-panel ring-frost-border rounded-xl border ring-1">
                  <div className="border-frost-border border-b px-4 py-3 sm:px-6 sm:py-4">
                    <h2 className="frost-text text-lg font-semibold">Configuration</h2>
                  </div>
                  <div className="grid grid-cols-1 gap-5 p-4 sm:gap-6 sm:p-6 md:grid-cols-2">
                    {Object.keys(config.parameters).map((key) => (
                      <React.Fragment key={key}>{renderParameterField(key, !isEditing)}</React.Fragment>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="frost-panel ring-frost-border min-w-0 rounded-xl border ring-1">
              <div className="border-frost-border border-b px-4 py-3 sm:px-6 sm:py-4">
                <h2 className="frost-text text-lg font-semibold">Metadata</h2>
              </div>
              <dl className="space-y-4 p-4 sm:p-6">
                <div>
                  <dt className="frost-text-muted text-xs font-medium">Authenticator ID</dt>
                  <dd className="mt-1 flex min-w-0 items-center gap-1">
                    <span className="frost-text min-w-0 truncate font-mono text-sm" title={authenticator.auth_id}>
                      {authenticator.auth_id}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Copy ID"
                      onClick={() => void handleCopyId(authenticator.auth_id)}
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                  </dd>
                </div>
                <div>
                  <dt className="frost-text-muted text-xs font-medium">Created At</dt>
                  <dd className="frost-text mt-1 text-sm">{new Date(authenticator.created_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="frost-text-muted text-xs font-medium">Updated At</dt>
                  <dd className="frost-text mt-1 text-sm">{new Date(authenticator.updated_at).toLocaleString()}</dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}

      <DeleteConfirmationDialog
        isOpen={showDeleteModal}
        title="Delete Authenticator"
        message={`Are you sure you want to delete "${authenticator?.auth_name || ''}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteModal(false)}
        loading={deleteAuthenticator.isPending}
      />
    </div>
  );
};

export default AuthenticatorDetailPage;
