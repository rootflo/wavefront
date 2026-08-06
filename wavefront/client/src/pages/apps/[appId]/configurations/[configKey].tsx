import floConsoleService from '@app/api';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { useGetConfiguration, useGetConfigurations } from '@app/hooks';
import { getConfigurationKey, getConfigurationsKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const ConfigurationDetail: React.FC = () => {
  const { app: appId, namespace, configKey } = useParams<{ app: string; namespace: string; configKey: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [valueText, setValueText] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const { data: value, isLoading: loadingValue } = useGetConfiguration(appId, namespace, configKey);

  // The detail endpoint returns the configuration document alone — it is the
  // same endpoint the workflow node calls, and that node's output has to be the
  // document. Description therefore comes from the list, which carries metadata
  // but no values. Saving is blocked until it has loaded, because PUT replaces
  // description too: sending an empty one before it arrives would silently wipe
  // it.
  const { data: configurations = [], isLoading: loadingMetadata } = useGetConfigurations(appId);
  const metadata = useMemo(
    () => configurations.find((item) => item.namespace === namespace && item.key === configKey),
    [configurations, namespace, configKey]
  );

  useEffect(() => {
    if (value !== undefined && value !== null) {
      setValueText(JSON.stringify(value, null, 2));
    }
  }, [value]);

  useEffect(() => {
    setDescription(metadata?.description ?? '');
  }, [metadata]);

  const parseError = useMemo(() => {
    if (!valueText.trim()) return 'Value is required';
    try {
      JSON.parse(valueText);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : 'Value must be valid JSON';
    }
  }, [valueText]);

  const handleSave = async () => {
    if (!namespace || !configKey || parseError) return;

    setSaving(true);
    try {
      const response = await floConsoleService.configurationService.upsertConfiguration(namespace, configKey, {
        value: JSON.parse(valueText),
        description: description.trim() || undefined,
      });

      if (response.data) {
        notifySuccess('Configuration saved successfully');
        queryClient.invalidateQueries({
          queryKey: getConfigurationKey(appId || '', namespace, configKey),
        });
        queryClient.invalidateQueries({
          queryKey: getConfigurationsKey(appId || ''),
        });
      } else {
        notifyError('Failed to save configuration');
      }
    } catch (error) {
      console.error('Error saving configuration:', error);
    } finally {
      setSaving(false);
    }
  };

  const loading = loadingValue || loadingMetadata;

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
                onClick={() => navigate(`/apps/${appId}/configurations`)}
                className="hover:text-foreground cursor-pointer"
              >
                Configurations
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>{configKey}</BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">{configKey}</h1>
          <p className="animate-fade-in mt-2 font-mono text-sm text-gray-600">{namespace}</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Button variant="outline" onClick={() => navigate(`/apps/${appId}/configurations`)}>
            Back
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={!!parseError || loading}>
            Save
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-6 overflow-y-auto">
        <div className="max-w-xl">
          <Label htmlFor="configuration-description">Description</Label>
          <Input
            id="configuration-description"
            className="mt-2"
            placeholder="Optional"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
          />
        </div>

        <div>
          <Label>Value</Label>
          <p className="mt-1 mb-2 text-sm text-gray-600">
            Replaced wholesale on save — the document is not merged into the stored one, so removing a field here
            removes it in storage.
          </p>
          {loading ? (
            <div className="h-[500px] w-full animate-pulse rounded-md bg-gray-100" />
          ) : (
            <CodeMirror
              value={valueText}
              onChange={setValueText}
              theme="dark"
              height="500px"
              className="w-full"
              extensions={[langs.json()]}
            />
          )}
          {parseError && <p className="mt-2 text-sm text-red-500">{parseError}</p>}
        </div>
      </div>
    </div>
  );
};

export default ConfigurationDetail;
