import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Skeleton } from '@app/components/ui/skeleton';
import { cn } from '@app/lib/utils';
import { Datasource } from '@app/types/datasource';
import { useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { Copy } from 'lucide-react';
import React from 'react';
import { ConnectionTest } from './connection-test';
import { DATASOURCE_TYPE_LABELS } from './datasource-types';
import { useParams } from 'react-router';
import { useGetDatasourceResources } from '@app/hooks';

dayjs.extend(relativeTime);

// Config keys whose values are never shown, only that they are set.
const SECRET_KEY = /pass|secret|token|key|credential|private|auth|signature/i;

const maskConfig = (value: unknown, key = ''): unknown => {
  if (SECRET_KEY.test(key) && value !== null && value !== undefined && value !== '') return '••••••••';
  if (Array.isArray(value)) return value.map((item) => maskConfig(item));
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, maskConfig(v, k)]));
  }
  return value;
};

const formatSetting = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const formatDate = (value?: string) =>
  value && dayjs(value).isValid() ? dayjs(value).format('DD MMM YYYY, HH:mm') : '—';

const Card = ({
  title,
  action,
  className,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) => (
  <section className={cn('frost-panel ring-frost-border rounded-xl border ring-1', className)}>
    <div className="border-frost-border flex items-center justify-between gap-3 border-b px-5 py-3.5">
      <h2 className="frost-text text-sm font-semibold">{title}</h2>
      {action}
    </div>
    <div className="p-5">{children}</div>
  </section>
);

const Stat = ({ label, value, loading }: { label: string; value: React.ReactNode; loading?: boolean }) => (
  <div className="frost-control ring-frost-border flex min-w-0 flex-col gap-1 rounded-xl px-4 py-3 ring-1">
    <span className="frost-text-muted text-xs">{label}</span>
    {loading ? (
      <Skeleton className="h-6 w-16" />
    ) : (
      <span className="frost-text truncate text-lg font-semibold">{value}</span>
    )}
  </div>
);

interface DatasourceInfoProps {
  datasource: Datasource;
  isFileStorage: boolean;
  dynamicQueryCount: number;
  lastTest: ConnectionTest | null;
  testing: boolean;
  onTest: () => void;
  onCopyId: (id: string) => void;
}

/** The Info tab: what the datasource is, whether it is reachable, how it is set up, and what's in it. */
const DatasourceInfo: React.FC<DatasourceInfoProps> = ({
  datasource,
  isFileStorage,
  dynamicQueryCount,
  lastTest,
  testing,
  onTest,
  onCopyId,
}) => {
  const { app: appId } = useParams<{ app: string }>();
  const tablesQuery = useGetDatasourceResources(appId, datasource.id, !isFileStorage);

  const lastActivityQuery = useQuery({
    queryKey: ['datasource-last-activity', datasource.id],
    queryFn: async () =>
      (await floConsoleService.datasourcesService.listDatasourceAuditLogs({ datasource_id: datasource.id, limit: 1 }))
        .data?.data ?? null,
    retry: false,
  });
  const activityForbidden = (lastActivityQuery.error as AxiosError | null)?.response?.status === 403;
  const lastActivity = lastActivityQuery.data?.logs?.[0];

  const settings = Object.entries((maskConfig(datasource.config ?? {}) as Record<string, unknown>) || {});

  return (
    <div className="grid w-full gap-6 lg:grid-cols-3">
      <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
        <div className={cn('grid gap-3', isFileStorage ? 'sm:grid-cols-2' : 'sm:grid-cols-3')}>
          {!isFileStorage && (
            <Stat
              label="Tables"
              loading={tablesQuery.isLoading}
              value={tablesQuery.error ? '—' : (tablesQuery.data?.length ?? 0)}
            />
          )}
          {!isFileStorage && <Stat label="Dynamic queries" value={dynamicQueryCount} />}
          <Stat
            label="Last change"
            loading={lastActivityQuery.isLoading}
            value={
              activityForbidden ? (
                <span className="frost-text-muted text-sm font-normal">Admins only</span>
              ) : lastActivity ? (
                <span title={formatDate(lastActivity.created_at)}>
                  {dayjs(lastActivity.created_at).fromNow()}
                  <span className="frost-text-muted ml-1.5 text-xs font-normal">{lastActivity.operation}</span>
                </span>
              ) : (
                'None yet'
              )
            }
          />
          {isFileStorage && <Stat label="Type" value={DATASOURCE_TYPE_LABELS[datasource.type] || datasource.type} />}
        </div>

        <Card
          title="Connection"
          action={
            <Button variant="outline" size="sm" onClick={onTest} loading={testing} disabled={testing}>
              Test now
            </Button>
          }
        >
          <div className="flex items-center gap-3">
            <span
              className={cn(
                'size-2.5 shrink-0 rounded-full',
                !lastTest ? 'bg-frost-text-subtle' : lastTest.ok ? 'bg-emerald-500' : 'bg-rose-500'
              )}
            />
            <div className="min-w-0">
              <p className="frost-text text-sm font-medium">
                {!lastTest ? 'Not tested yet' : lastTest.ok ? 'Connected' : 'Connection failed'}
              </p>
              <p className="frost-text-muted text-xs">
                {lastTest
                  ? `Last tested ${dayjs(lastTest.at).fromNow()} from this browser`
                  : 'Run a test to check the datasource is reachable with its current settings.'}
              </p>
            </div>
          </div>
        </Card>

        <Card title="Settings">
          {settings.length === 0 ? (
            <p className="frost-text-muted text-sm">No settings stored.</p>
          ) : (
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {settings.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="frost-text-muted text-xs font-medium">{key}</dt>
                  <dd className="frost-text mt-1 truncate font-mono text-sm" title={formatSetting(value)}>
                    {formatSetting(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <p className="frost-text-subtle mt-4 text-xs">Passwords, keys and tokens are hidden. Edit to change them.</p>
        </Card>
      </div>

      <div className="flex min-w-0 flex-col gap-6">
        {/* Stretches to the bottom of the left column so the two sides end level. */}
        <Card title="Details" className="flex-1">
          <dl className="space-y-4">
            <div>
              <dt className="frost-text-muted text-xs font-medium">Description</dt>
              <dd className="frost-text mt-1 text-sm">{datasource.description || '—'}</dd>
            </div>
            <div>
              <dt className="frost-text-muted text-xs font-medium">Datasource ID</dt>
              <dd className="mt-1 flex items-center gap-1">
                <span className="frost-text truncate font-mono text-sm" title={datasource.id}>
                  {datasource.id}
                </span>
                <Button variant="ghost" size="sm" title="Copy ID" onClick={() => onCopyId(datasource.id)}>
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </dd>
            </div>
            <div>
              <dt className="frost-text-muted text-xs font-medium">Type</dt>
              <dd className="frost-text mt-1 text-sm">
                {DATASOURCE_TYPE_LABELS[datasource.type] || datasource.type || '—'}
              </dd>
            </div>
            <div>
              <dt className="frost-text-muted text-xs font-medium">Created</dt>
              <dd className="frost-text mt-1 text-sm">{formatDate(datasource.created_at)}</dd>
            </div>
            <div>
              <dt className="frost-text-muted text-xs font-medium">Updated</dt>
              <dd className="frost-text mt-1 text-sm">{formatDate(datasource.updated_at)}</dd>
            </div>
          </dl>
        </Card>
      </div>
    </div>
  );
};

export default DatasourceInfo;
