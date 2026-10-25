import MobileBackButton from '@app/components/MobileBackButton';
import DetailActions from '@app/components/DetailActions';
import PageTitle from '@app/components/PageTitle';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { useGetConfiguration, useGetConfigurations, useSaveConfiguration } from '@app/hooks';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { formatAppName } from '@app/utils/string-formatting';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const ConfigurationDetail: React.FC = () => {
  const { app: appId, namespace, configKey } = useParams<{ app: string; namespace: string; configKey: string }>();
  const navigate = useNavigate();
  const saveConfiguration = useSaveConfiguration(appId);

  const [valueText, setValueText] = useState('');
  const [description, setDescription] = useState('');

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

  const handleSave = () => {
    if (!namespace || !configKey || parseError) return;

    saveConfiguration.mutate({
      namespace,
      key: configKey,
      data: { value: JSON.parse(valueText), description: description.trim() || undefined },
    });
  };

  const loading = loadingValue || loadingMetadata;

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb
        items={[{ label: 'Configurations', to: `/apps/${appId}/configurations` }, { label: configKey }]}
      />

      <div className="mb-8 flex w-full flex-col items-start gap-4 sm:flex-row sm:justify-between">
        <div>
          <div className="flex min-w-0 items-center gap-2">
            <MobileBackButton to={`/apps/${appId}/configurations`} label="Back to configurations" />
            <PageTitle className="animate-fade-in">{formatAppName(configKey)}</PageTitle>
          </div>
          <p className="animate-fade-in frost-text-muted mt-2 font-mono text-sm">{namespace}</p>
        </div>
        <DetailActions
          editing
          cancelLabel="Back"
          onCancel={() => navigate(`/apps/${appId}/configurations`)}
          onSave={handleSave}
          saving={saveConfiguration.isPending}
          saveDisabled={!!parseError || loading}
        />
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
          <p className="frost-text-muted mt-1 mb-2 text-sm">
            Replaced wholesale on save — the document is not merged into the stored one, so removing a field here
            removes it in storage.
          </p>
          {loading ? (
            <div className="bg-muted h-[500px] w-full animate-pulse rounded-md" />
          ) : (
            <CodeEditor
              value={valueText}
              onChange={setValueText}
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
