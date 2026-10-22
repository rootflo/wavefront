import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { FlaskConical, Save } from 'lucide-react';
import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import floConsoleService from '@app/api';
import {
  EnforcementMode,
  FailureMode,
  GuardrailAdapterConfig,
  StreamPreference,
  WorkflowStage,
} from '@app/api/guardrails-service';
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
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import AdapterCard from './AdapterCard';
import PolicyTestPanel from './PolicyTestPanel';
import { ADAPTER_META, DEFAULT_UNAVAILABLE_HINT, adapterLabel } from './adapter-meta';

/**
 * Canonical serialisation of a JSON-ish value: object keys and array members
 * both ordered.
 *
 * Nothing in a policy payload is order-significant — `adapters`, `stages` and
 * the PII `entities` list are all sets — but the editor rebuilds them in
 * whichever order you clicked: toggling a check off and on appends it at
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
const fingerprintPolicy = (
  isEnabled: boolean,
  mode: EnforcementMode,
  adapters: GuardrailAdapterConfig[],
  stream: StreamPreference
): string => canonicalJson({ is_enabled: isEnabled, mode, adapters, stream });

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
  const [stream, setStream] = useState<StreamPreference>('BUFFERED');
  const [saving, setSaving] = useState(false);
  const [testOpen, setTestOpen] = useState(false);

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
    const loadedStream = policy?.stream ?? 'BUFFERED';

    setIsEnabled(loadedEnabled);
    setMode(loadedMode);
    setAdapters(loadedAdapters);
    setStream(loadedStream);
    setSavedFingerprint(fingerprintPolicy(loadedEnabled, loadedMode, loadedAdapters, loadedStream));
  }, [policy, namespace]);

  const draftFingerprint = useMemo(
    () => fingerprintPolicy(isEnabled, mode, adapters, stream),
    [isEnabled, mode, adapters, stream]
  );
  const hasUnsavedChanges = savedFingerprint !== null && draftFingerprint !== savedFingerprint;

  const configuredByName = useMemo(() => new Map(adapters.map((adapter) => [adapter.name, adapter])), [adapters]);

  // Checks stored in the policy that this deployment cannot run.
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
        // Sent even when unchanged: the server replaces policy_config
        // wholesale, so leaving it out would revert the namespace to
        // buffered without anything on this page saying so.
        stream,
      });
      // The refetch below lands on these same values and resets the baseline
      // anyway, but not until it returns. Moving the baseline now stops the
      // indicator from sitting there over an already-saved policy.
      setSavedFingerprint(draftFingerprint);
      queryClient.invalidateQueries({ queryKey: getGuardrailPolicyKey(appId || '', namespace) });
      queryClient.invalidateQueries({ queryKey: getGuardrailPoliciesKey(appId || '') });
      notifySuccess('Guardrail policy saved');
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to save guardrail policy');
    } finally {
      setSaving(false);
    }
  };

  const namespaceOptions = namespaces.length ? namespaces.map((item) => item.name) : ['default'];

  return (
    <div className="flex h-full w-full flex-col p-4 max-md:overflow-y-auto sm:p-8">
      <Breadcrumb className="mb-4 hidden md:block">
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

      <ListHeader
        title="Guardrails & Security"
        subtitle={<>AI safety policy for {selectedApp?.app_name}</>}
        filters={
          <>
            <FilterSelect
              label="Namespace"
              value={namespace}
              onValueChange={setNamespace}
              options={namespaceOptions.map((name) => ({ value: name, label: name }))}
            />
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
                className="flex shrink-0 items-center gap-1.5 rounded-full border border-amber-400/50 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-800 dark:text-amber-300"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true" />
                Unsaved changes
              </span>
            )}
          </>
        }
        // The panel sits below the list of checks, which is long enough that it is off screen on load. This header
        // is outside the scroll container, so it is the one place a jump-to control is always reachable.
        secondary={[
          {
            label: 'Test policy',
            icon: FlaskConical,
            onClick: () => setTestOpen(true),
            disabled: isLoading,
          },
        ]}
        primary={{
          label: saving ? 'Saving...' : 'Save policy',
          icon: Save,
          onClick: handleSave,
          disabled: saving || isLoading,
        }}
      />

      {isLoading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="pb-8 max-md:flex-none md:min-h-0 md:flex-1 md:overflow-y-auto">
          {/*
            Two columns once there is room for them. The policy-wide switches
            are short and the list of checks is very long, so the left column is
            sticky: the master switch and enforcement mode stay reachable while
            scrolling a long entity selection, which is exactly when you want to
            flip back to Monitor.
          */}
          <div className="grid max-w-[1400px] grid-cols-1 items-start gap-6 lg:min-h-full lg:grid-cols-[340px_minmax(0,1fr)]">
            <section className="frost-card ring-frost-border rounded-2xl border p-6 ring-1 lg:self-stretch">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <Label className="frost-text text-base font-semibold">Enable guardrails</Label>
                  <Switch checked={isEnabled} onCheckedChange={setIsEnabled} />
                </div>
                <p className="frost-text-muted mt-1.5 text-sm">
                  The master switch for <span className="font-medium">{namespace}</span>. While off, none of the checks
                  below run.
                </p>
              </div>

              <Separator className="my-5" />

              <div>
                <div className="flex items-center justify-between gap-3">
                  <Label className="frost-text text-base font-semibold">Enforcement mode</Label>
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
                <p className="frost-text-muted mt-1.5 text-sm">
                  {mode === 'MONITOR'
                    ? 'Monitor records what the policy would have done without blocking or redacting anything. Start here to measure false positives against real traffic.'
                    : 'Enforce blocks prompts and redacts responses. Switch here once monitor mode shows an acceptable false-positive rate.'}
                </p>
              </div>

              <Separator className="my-5" />

              <div>
                <div className="flex items-center justify-between gap-3">
                  <Label className="frost-text text-base font-semibold">Stream responses</Label>
                  <Switch
                    checked={stream === 'INCREMENTAL'}
                    disabled={!isEnabled}
                    onCheckedChange={(checked) => setStream(checked ? 'INCREMENTAL' : 'BUFFERED')}
                  />
                </div>
                <p className="frost-text-muted mt-1.5 text-sm">
                  {stream === 'INCREMENTAL'
                    ? 'Responses appear as they are written, with the end held back until it has been checked. Only providers whose findings are span-local support this; if any configured check does not, the whole response is withheld regardless of this setting.'
                    : 'Responses are withheld until the whole of them has been checked, so nothing reaches the user before the verdict. Turning this on trades some of that delay for text appearing as it is written.'}
                </p>
              </div>
            </section>

            <div>
              <div className="mb-4">
                <h2 className="frost-text text-lg font-semibold">Safety checks</h2>
                <p className="frost-text-muted mt-1 text-sm">
                  Each check runs at the stages you select. Checks not enabled here are never called.
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
                  <p className="frost-text-subtle text-sm">
                    No safety checks are available on this deployment. Enabling guardrails without a working check would
                    block all traffic for this namespace, so none can be selected here.
                  </p>
                )}
                {strandedAdapters.map((name) => (
                  <div
                    key={name}
                    className="flex items-center justify-between gap-4 rounded-lg border border-red-400/50 bg-red-500/10 p-4"
                  >
                    <div>
                      <p className="text-sm font-medium text-red-800 dark:text-red-300">
                        {adapterLabel(name)} — not available on this deployment
                      </p>
                      <p className="mt-1 text-sm text-red-800 dark:text-red-300">
                        This check is saved in the policy but cannot run, so in Enforce mode it blocks every request for
                        this namespace. Remove it, or switch back to Monitor while you fix the deployment.
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => handleToggleAdapter(name, false)}>
                      Remove
                    </Button>
                  </div>
                ))}
                {unavailableAdapters.map((name) => (
                  <div key={name} className="border-frost-border bg-frost-glass rounded-lg border border-dashed p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="frost-text-muted text-sm font-medium">
                          {adapterLabel(name)}
                          <span className="bg-frost-glass-strong frost-text-muted ml-2 rounded px-2 py-0.5 text-xs font-normal">
                            Not available
                          </span>
                        </p>
                        {ADAPTER_META[name]?.description && (
                          <p className="frost-text-subtle mt-1 text-sm">{ADAPTER_META[name].description}</p>
                        )}
                      </div>
                      <Switch checked={false} disabled />
                    </div>
                    <p className="frost-text-muted mt-3 text-sm">
                      {ADAPTER_META[name]?.unavailableHint ?? DEFAULT_UNAVAILABLE_HINT}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent className="flex h-[760px] max-h-[calc(100dvh-2rem)] max-w-5xl min-w-0 flex-col overflow-hidden lg:max-w-5xl">
          <DialogHeader>
            <DialogTitle>Test this policy</DialogTitle>
            <DialogDescription>
              Runs the settings on this page, saved or not, through the real engine. Nothing is stored.
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto pt-2 lg:overflow-hidden">
            <PolicyTestPanel
              hideHeading
              isEnabled={isEnabled}
              mode={mode}
              adapters={adapters}
              stream={stream}
              piiGroups={piiEntities?.groups}
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default GuardrailsManagement;
