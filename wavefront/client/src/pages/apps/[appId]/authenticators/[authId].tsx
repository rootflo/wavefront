import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Badge } from '@app/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
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
import { getAuthenticatorKey, getAuthenticatorsKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, extractErrorMessage, formatAppName } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import {
  getBooleanNestedParameter,
  getBooleanParameter,
  getNumberOrStringNestedParameter,
  getNumberOrStringParameter,
  getStringNestedParameter,
  getStringParameter,
} from '@app/utils/parameter-helpers';
import { useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const formatFieldName = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const fieldId = (...parts: string[]) => ['authenticator', ...parts].join('-');

const AuthenticatorDetailPage: React.FC = () => {
  const { app, authId } = useParams<{ app: string; authId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [togglingEnabled, setTogglingEnabled] = useState(false);

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

  const handleSave = async () => {
    if (!authId) return;

    setSaveLoading(true);
    try {
      await floConsoleService.authenticatorService.updateAuthenticator(authId, {
        auth_desc: authDesc.trim() || null,
        config: cleanParameters(parameters),
      });
      notifySuccess('Authenticator updated successfully');
      setIsEditing(false);
      queryClient.invalidateQueries({
        queryKey: getAuthenticatorKey(app || '', authId),
      });
      queryClient.invalidateQueries({ queryKey: getAuthenticatorsKey(app || '') });
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update authenticator');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!authId) return;

    setDeleting(true);
    try {
      await floConsoleService.authenticatorService.deleteAuthenticator(authId);
      notifySuccess('Authenticator deleted successfully');
      navigate(`/apps/${app}/authenticators`);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete authenticator');
    } finally {
      setDeleting(false);
    }
  };

  const handleToggleEnabled = async (enabled: boolean) => {
    if (!authId || !authenticator) return;

    setTogglingEnabled(true);
    try {
      if (enabled) {
        await floConsoleService.authenticatorService.enableAuthenticator(authId);
        notifySuccess('Authenticator enabled successfully');
      } else {
        await floConsoleService.authenticatorService.disableAuthenticator(authId);
        notifySuccess('Authenticator disabled successfully');
      }
      queryClient.invalidateQueries({
        queryKey: getAuthenticatorKey(app || '', authId),
      });
      queryClient.invalidateQueries({ queryKey: getAuthenticatorsKey(app || '') });
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to toggle authenticator');
    } finally {
      setTogglingEnabled(false);
    }
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
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-4">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${app}/authenticators`)}
                className="hover:text-foreground cursor-pointer"
              >
                Authenticators
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{authenticator?.auth_name || authId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {authenticatorLoading ? (
        <p className="frost-text-muted text-sm">Loading authenticator...</p>
      ) : !authenticator ? (
        <p className="text-sm text-red-500">Authenticator not found</p>
      ) : (
        <>
          <div className="mb-8 flex w-full items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="frost-text text-3xl font-bold">{formatAppName(authenticator.auth_name)}</h1>
                {badge && (
                  <Badge variant="secondary" className={`${badge.bg} ${badge.text} border-0 font-normal`}>
                    {config?.name || authenticator.auth_type}
                  </Badge>
                )}
                <Switch
                  checked={authenticator.is_enabled}
                  onCheckedChange={(checked) => void handleToggleEnabled(checked)}
                  disabled={togglingEnabled}
                  title={authenticator.is_enabled ? 'Enabled' : 'Disabled'}
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              {!isEditing ? (
                <>
                  <Button variant="outline" onClick={() => setIsEditing(true)}>
                    Edit
                  </Button>
                  <Button variant="destructive" onClick={() => setShowDeleteModal(true)}>
                    Delete
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={handleCancel} disabled={saveLoading}>
                    Cancel
                  </Button>
                  <Button onClick={() => void handleSave()} loading={saveLoading}>
                    Save
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="grid w-full gap-6 lg:grid-cols-3">
            <div className="flex flex-col gap-6 lg:col-span-2">
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
                  <div className="border-b border-[#EFF0F1] px-6 py-4">
                    <h2 className="frost-text text-lg font-semibold">Configuration</h2>
                  </div>
                  <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-2">
                    {Object.keys(config.parameters).map((key) => (
                      <React.Fragment key={key}>{renderParameterField(key, !isEditing)}</React.Fragment>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="frost-panel ring-frost-border rounded-xl border ring-1">
              <div className="border-b border-[#EFF0F1] px-6 py-4">
                <h2 className="frost-text text-lg font-semibold">Metadata</h2>
              </div>
              <dl className="space-y-4 p-6">
                <div>
                  <dt className="frost-text-muted text-xs font-medium">Authenticator ID</dt>
                  <dd className="mt-1 flex items-center gap-1">
                    <span className="frost-text truncate font-mono text-sm" title={authenticator.auth_id}>
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
        loading={deleting}
      />
    </div>
  );
};

export default AuthenticatorDetailPage;
