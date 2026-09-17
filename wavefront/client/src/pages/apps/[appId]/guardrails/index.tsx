import floConsoleService from '@app/api';
import { EnforcementMode, FailureMode, GuardrailAdapterConfig, WorkflowStage } from '@app/api/guardrails-service';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Separator } from '@app/components/ui/separator';
import { Skeleton } from '@app/components/ui/skeleton';
import { Switch } from '@app/components/ui/switch';
import {
  useGetGuardrailAdapters,
  useGetGuardrailPiiEntities,
  useGetGuardrailPolicy,
  useGetNamespaces,
} from '@app/hooks';
import { getGuardrailPoliciesKey, getGuardrailPolicyKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import AdapterCard from './AdapterCard';
import PolicyTestPanel, { PolicyTestHandle } from './PolicyTestPanel';
import { ADAPTER_META } from './adapter-meta';

/**
 * Canonical serialisation of a JSON-ish value: object keys and array members
 * both ordered.
 *
 * Nothing in a policy payload is order-significant — `adapters`, `stages` and
 * the PII `entities` list are all sets — but the editor rebuilds them in
 * whichever order you clicked: toggling a provider off and on appends it at
 * the end, and so does ticking a stage or an entity. Comparing raw
 * `JSON.stringify` output would call those unsaved changes, and an indicator
 * that cries wolf trains you to ignore the one time it is right.
 */
const canonicalJson = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).sort().join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
};

/** Value-equality fingerprint of everything this editor can change. */
const fingerprintPolicy = (isEnabled: boolean, mode: EnforcementMode, adapters: GuardrailAdapterConfig[]): string =>
  canonicalJson({ is_enabled: isEnabled, mode, adapters });

const GuardrailsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [namespace, setNamespace] = useState<string>('default');
  const [isEnabled, setIsEnabled] = useState(false);
  const [mode, setMode] = useState<EnforcementMode>('MONITOR');
  const [adapters, setAdapters] = useState<GuardrailAdapterConfig[]>([]);
  const [saving, setSaving] = useState(false);
  const testPanelRef = useRef<PolicyTestHandle>(null);

  const { data: namespaces = [] } = useGetNamespaces(appId);
  const { data: adapterInfo } = useGetGuardrailAdapters(appId);
  // Memoised because `?? []` allocates a new array on every render, which
  // would invalidate the useMemo below each time.
  const supportedAdapters = useMemo(() => adapterInfo?.adapters ?? [], [adapterInfo]);
  const unavailableAdapters = adapterInfo?.unavailable ?? [];
  const { data: policy, isLoading } = useGetGuardrailPolicy(appId, namespace);
  const { data: piiEntities } = useGetGuardrailPiiEntities(appId);

  // Fingerprint of the policy as it stands on the server. Null until the
  // first load, so nothing is reported as unsaved before there is a baseline
  // to compare against.
  const [savedFingerprint, setSavedFingerprint] = useState<string | null>(null);

  // Reset the form whenever a different namespace's policy arrives, so the
  // editor never shows one namespace's settings under another's name.
  //
  // The baseline is captured here, in the same effect, rather than derived
  // from `policy` during render: on the render the new data lands the form
  // still holds the previous namespace's values, so a render-time comparison
  // would flash "Unsaved changes" over a form nobody had touched.
  useEffect(() => {
    const loadedEnabled = policy?.is_enabled ?? false;
    const loadedMode = policy?.mode ?? 'MONITOR';
    const loadedAdapters = policy?.adapters ?? [];

    setIsEnabled(loadedEnabled);
    setMode(loadedMode);
    setAdapters(loadedAdapters);
    setSavedFingerprint(fingerprintPolicy(loadedEnabled, loadedMode, loadedAdapters));
  }, [policy, namespace]);

  const draftFingerprint = useMemo(() => fingerprintPolicy(isEnabled, mode, adapters), [isEnabled, mode, adapters]);
  const hasUnsavedChanges = savedFingerprint !== null && draftFingerprint !== savedFingerprint;

  const configuredByName = useMemo(() => new Map(adapters.map((adapter) => [adapter.name, adapter])), [adapters]);

  // Providers stored in the policy that this deployment cannot run.
  //
  // These have to be surfaced, not filtered out. An unregistered adapter fails
  // closed, so one left in a policy blocks every request in the namespace --
  // and if it is only rendered when available, it is invisible here while
  // still being resubmitted on every save, with no way to remove it.
  const strandedAdapters = useMemo(
    () => adapters.map((adapter) => adapter.name).filter((name) => !supportedAdapters.includes(name)),
    [adapters, supportedAdapters]
  );

  const handleToggleAdapter = (name: string, enabled: boolean) => {
    setAdapters((current) => {
      if (!enabled) {
        return current.filter((adapter) => adapter.name !== name);
      }
      const meta = ADAPTER_META[name];
      return [
        ...current,
        {
          name,
          stages: meta?.defaultStages ?? (['BEFORE_MODEL'] as WorkflowStage[]),
          on_error: (meta?.defaultOnError ?? 'FAIL_OPEN') as FailureMode,
          timeout_seconds: 5,
          options: { ...(meta?.defaultOptions ?? {}) },
        },
      ];
    });
  };

  const handleUpdateAdapter = (name: string, patch: Partial<GuardrailAdapterConfig>) => {
    setAdapters((current) => current.map((adapter) => (adapter.name === name ? { ...adapter, ...patch } : adapter)));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await floConsoleService.guardrailsService.updatePolicy(namespace, {
        is_enabled: isEnabled,
        mode,
        adapters,
      });
      // The refetch below lands on these same values and resets the baseline
      // anyway, but not until it returns. Moving the baseline now stops the
      // indicator from sitting there over an already-saved policy.
      setSavedFingerprint(draftFingerprint);
      queryClient.invalidateQueries({ queryKey: getGuardrailPolicyKey(appId || '', namespace) });
      queryClient.invalidateQueries({ queryKey: getGuardrailPoliciesKey(appId || '') });
      notifySuccess('Guardrail policy saved');
    } catch (error) {
      notifyError(extractErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const namespaceOptions = namespaces.length ? namespaces.map((item) => item.name) : ['default'];

  return (
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-6">
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
                onClick={() => navigate(`/apps/${appId}/guardrails`)}
                className="hover:text-foreground cursor-pointer"
              >
                Guardrails
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">Guardrails &amp; Security</h1>
          <p className="animate-fade-in mt-2 text-gray-600">AI safety policy for {selectedApp?.app_name}</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Select value={namespace} onValueChange={setNamespace}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Namespace" />
            </SelectTrigger>
            <SelectContent>
              {namespaceOptions.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/*
            The panel sits below the provider list, which is long enough that
            it is off screen on load. This header is outside the scroll
            container, so it is the one place a jump-to control is always
            reachable.
          */}
          <Button variant="outline" onClick={() => testPanelRef.current?.focus()} disabled={isLoading}>
            Test policy
          </Button>
          {/*
            Next to Save, not near the edit that caused it: the test panel runs
            the draft, so a policy can be built, verified and left unsaved
            without anything contradicting you. This header stays on screen
            while the form scrolls, so the reminder is visible from wherever
            the last edit was made.
          */}
          {hasUnsavedChanges && (
            <span
              role="status"
              title="These settings are not live yet. Agents and workflows in this namespace keep using the saved policy until you save."
              className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true" />
              Unsaved changes
            </span>
          )}
          <Button onClick={handleSave} disabled={saving || isLoading}>
            {saving ? 'Saving...' : 'Save policy'}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="overflow-y-auto pb-8">
          {/*
            Two columns once there is room for them. The policy-wide switches
            are short and the provider list is very long, so the left column is
            sticky: the master switch and enforcement mode stay reachable while
            scrolling a long entity selection, which is exactly when you want to
            flip back to Monitor.
          */}
          <div className="grid max-w-[1400px] grid-cols-1 items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
            <section className="rounded-lg border border-gray-200 p-6 lg:sticky lg:top-0 lg:self-start">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <Label className="text-base font-semibold">Enable guardrails</Label>
                  <Switch checked={isEnabled} onCheckedChange={setIsEnabled} />
                </div>
                <p className="mt-1.5 text-sm text-gray-600">
                  The master switch for <span className="font-medium">{namespace}</span>. While off, no safety provider
                  is called and no checks run.
                </p>
              </div>

              <Separator className="my-5" />

              <div>
                <div className="flex items-center justify-between gap-3">
                  <Label className="text-base font-semibold">Enforcement mode</Label>
                  <Select value={mode} onValueChange={(value) => setMode(value as EnforcementMode)}>
                    <SelectTrigger className="w-[130px]" disabled={!isEnabled}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MONITOR">Monitor</SelectItem>
                      <SelectItem value="ENFORCE">Enforce</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="mt-1.5 text-sm text-gray-600">
                  {mode === 'MONITOR'
                    ? 'Monitor records what the policy would have done without blocking or redacting anything. Start here to measure false positives against real traffic.'
                    : 'Enforce blocks prompts and redacts responses. Switch here once monitor mode shows an acceptable false-positive rate.'}
                </p>
              </div>
            </section>

            <div>
              {/*
                Opaque background and a z-index, not just `sticky`: the provider
                cards scroll underneath this, and a transparent header would let
                their text show through it.
              */}
              <div className="sticky top-0 z-10 bg-white pb-4">
                <h2 className="text-lg font-semibold text-gray-900">Safety providers</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Each provider runs at the stages you select. Providers not enabled here are never called.
                </p>
              </div>
              <div className="flex flex-col gap-4">
                {supportedAdapters.map((name) => (
                  <AdapterCard
                    key={name}
                    name={name}
                    config={configuredByName.get(name)}
                    disabled={!isEnabled}
                    onToggle={(enabled) => handleToggleAdapter(name, enabled)}
                    onChange={(patch) => handleUpdateAdapter(name, patch)}
                    piiGroups={piiEntities?.groups}
                  />
                ))}
                {supportedAdapters.length === 0 && (
                  <p className="text-sm text-gray-500">
                    No safety providers are available on this deployment. Enabling guardrails without a working provider
                    would block all traffic for this namespace, so none can be selected here.
                  </p>
                )}
                {strandedAdapters.map((name) => (
                  <div
                    key={name}
                    className="flex items-center justify-between gap-4 rounded-lg border border-red-300 bg-red-50 p-4"
                  >
                    <div>
                      <p className="text-sm font-medium text-red-900">{name} — not available on this deployment</p>
                      <p className="mt-1 text-sm text-red-700">
                        This provider is saved in the policy but cannot run, so in Enforce mode it blocks every request
                        for this namespace. Remove it, or switch back to Monitor while you fix the deployment.
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => handleToggleAdapter(name, false)}>
                      Remove
                    </Button>
                  </div>
                ))}
                {unavailableAdapters.map((name) => (
                  <div key={name} className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium text-gray-700">
                          {ADAPTER_META[name]?.title ?? name}
                          <span className="ml-2 rounded bg-gray-200 px-2 py-0.5 text-xs font-normal text-gray-600">
                            Not installed
                          </span>
                        </p>
                        {ADAPTER_META[name]?.description && (
                          <p className="mt-1 text-sm text-gray-500">{ADAPTER_META[name].description}</p>
                        )}
                      </div>
                      <Switch checked={false} disabled />
                    </div>
                    <p className="mt-3 text-sm text-gray-600">
                      {name === 'azure_content_safety'
                        ? 'Set AZURE_CONTENT_SAFETY_ENDPOINT and AZURE_CONTENT_SAFETY_KEY on the server, then restart it. This provider becomes selectable here once it loads.'
                        : 'This provider is missing a server-side dependency. Install it and restart the server to make it selectable here.'}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="max-w-[1400px]">
            <Separator className="my-6" />
            <PolicyTestPanel ref={testPanelRef} isEnabled={isEnabled} mode={mode} adapters={adapters} />
          </div>
        </div>
      )}
    </div>
  );
};

export default GuardrailsManagement;
