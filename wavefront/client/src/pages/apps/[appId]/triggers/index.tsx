import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import { ResourceListSkeleton } from '@app/components/ResourceList';
import ResourceCard from '@app/components/ResourceCard';
import { Zap, Play, Pause, RotateCcw } from 'lucide-react';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { TRIGGER_STATUS_BADGE_CLASS, TRIGGER_STATUS_OPTIONS } from '@app/constants/trigger';
import {
  useDeleteTrigger,
  useGetAgents,
  useGetEmailConnections,
  useGetTriggers,
  useGetWorkflows,
  useRetryTrigger,
  useSetTriggerPaused,
} from '@app/hooks';
import { cn } from '@app/lib/utils';
import { useDashboardStore } from '@app/store';
import { Trigger } from '@app/types/trigger';
import { useMemo, useState } from 'react';
import { useParams } from 'react-router';
import CreateTriggerDialog from './CreateTriggerDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const getSubjectRegex = (trigger: Trigger) => {
  const filter = trigger.filter_config;
  if (!filter || typeof filter !== 'object') return null;
  const subjectRegex = (filter as { subject_regex?: unknown }).subject_regex;
  return typeof subjectRegex === 'string' && subjectRegex.trim() ? subjectRegex : null;
};

const getMailboxEmail = (trigger: Trigger) => {
  const config = trigger.provider_config;
  if (!config || typeof config !== 'object') return null;
  const email = config.email_address;
  return typeof email === 'string' && email.trim() ? email : null;
};

const TriggersPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const setTriggerPaused = useSetTriggerPaused(appId);
  const retryTrigger = useRetryTrigger(appId);
  const deleteTriggerMutation = useDeleteTrigger(appId);
  const deletion = useDeleteConfirm<Trigger>((item) => deleteTriggerMutation.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [formOpen, setFormOpen] = useState(false);

  const { data: triggers = [], isLoading } = useGetTriggers(appId);
  const { data: emailConnections = [] } = useGetEmailConnections(appId);
  const { data: agents = [] } = useGetAgents(appId);
  const { data: workflows = [] } = useGetWorkflows(appId);

  const connectionLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const connection of emailConnections) {
      map.set(connection.id, connection.mailbox_email || connection.name || connection.id);
    }
    return map;
  }, [emailConnections]);

  const entityLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.id, agent.name);
    }
    for (const workflow of workflows) {
      map.set(workflow.id, workflow.name);
    }
    return map;
  }, [agents, workflows]);

  const filteredTriggers = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return triggers.filter((trigger) => {
      if (statusFilter !== 'all' && trigger.status !== statusFilter) return false;
      if (!term) return true;
      const mailbox =
        getMailboxEmail(trigger) || connectionLabelById.get(trigger.connection_id) || trigger.connection_id;
      const entityName = entityLabelById.get(trigger.entity_id) || trigger.entity_id;
      return matchesSearch(
        term,
        trigger.name,
        trigger.provider,
        trigger.status,
        trigger.entity_type,
        entityName,
        mailbox,
        trigger.namespace,
        getSubjectRegex(trigger)
      );
    });
  }, [triggers, searchTerm, statusFilter, connectionLabelById, entityLabelById]);

  const handlePauseResume = (trigger: Trigger) => {
    setTriggerPaused.mutate({ triggerId: trigger.id, paused: trigger.status !== 'paused' });
  };

  const handleRetry = (trigger: Trigger) => {
    retryTrigger.mutate(trigger.id);
  };

  /** Disables just the row whose pause/resume or retry is in flight. */
  const isActing = (triggerId: string) =>
    (setTriggerPaused.isPending && setTriggerPaused.variables?.triggerId === triggerId) ||
    (retryTrigger.isPending && retryTrigger.variables === triggerId);

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-4 max-md:overflow-y-auto sm:p-8">
      <PageBreadcrumb items={[{ label: 'Triggers', to: `/apps/${appId}/triggers` }]} />

      <ListHeader
        title="Triggers"
        count={filteredTriggers.length || undefined}
        subtitle={<>Run agents and workflows from inbound email for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search triggers' }}
        filters={
          <FilterSelect
            label="Status"
            value={statusFilter}
            onValueChange={setStatusFilter}
            allValue="all"
            options={TRIGGER_STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
          />
        }
        primary={{ label: 'Create trigger', onClick: () => setFormOpen(true) }}
      />

      {isLoading ? (
        <ResourceListSkeleton view="table" />
      ) : filteredTriggers.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No triggers"
            description="Create a trigger to watch a Gmail inbox and run an agent or workflow when mail arrives"
            actionText="Create Trigger"
            onActionClick={() => setFormOpen(true)}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1 max-md:flex-none">
          <div data-mobile-cards className="flex flex-col gap-3 pb-24 md:hidden">
            {filteredTriggers.map((trigger) => {
              const mailbox =
                getMailboxEmail(trigger) || connectionLabelById.get(trigger.connection_id) || trigger.connection_id;
              const entityName = entityLabelById.get(trigger.entity_id) || trigger.entity_id;
              const subjectRegex = getSubjectRegex(trigger);
              const canPauseResume = trigger.status === 'active' || trigger.status === 'paused';
              const canRetry = trigger.status === 'error';
              return (
                <ResourceCard
                  key={trigger.id}
                  icon={Zap}
                  title={trigger.name}
                  description={trigger.last_error || `Runs ${entityName} (${trigger.entity_type})`}
                  metadata={[
                    {
                      label: 'Status',
                      value: trigger.status.replace('_', ' '),
                      className: cn('capitalize', TRIGGER_STATUS_BADGE_CLASS[trigger.status] || ''),
                    },
                    { label: 'Mailbox', value: mailbox },
                    { label: 'Filter', value: subjectRegex || 'All subjects', isMono: true },
                    { label: 'Updated', value: formatDateTime(trigger.updated_at) },
                  ]}
                  onDeleteClick={() => deletion.ask(trigger)}
                  deleteTitle="Delete trigger"
                  extraActions={[
                    ...(canPauseResume
                      ? [
                          {
                            label: trigger.status === 'paused' ? 'Resume' : 'Pause',
                            icon: trigger.status === 'paused' ? Play : Pause,
                            disabled: isActing(trigger.id),
                            onClick: () => void handlePauseResume(trigger),
                          },
                        ]
                      : []),
                    ...(canRetry
                      ? [
                          {
                            label: 'Retry',
                            icon: RotateCcw,
                            disabled: isActing(trigger.id),
                            onClick: () => void handleRetry(trigger),
                          },
                        ]
                      : []),
                  ]}
                />
              );
            })}
          </div>
          <div className="max-md:hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Mailbox</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Filter</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTriggers.map((trigger) => {
                  const mailbox =
                    getMailboxEmail(trigger) || connectionLabelById.get(trigger.connection_id) || trigger.connection_id;
                  const entityName = entityLabelById.get(trigger.entity_id) || trigger.entity_id;
                  const subjectRegex = getSubjectRegex(trigger);
                  const canPauseResume = trigger.status === 'active' || trigger.status === 'paused';
                  const canRetry = trigger.status === 'error';

                  return (
                    <TableRow key={trigger.id}>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className={cn('font-normal capitalize', TRIGGER_STATUS_BADGE_CLASS[trigger.status] || '')}
                        >
                          {trigger.status.replace('_', ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[180px]">
                        <div className="truncate font-medium" title={trigger.name}>
                          {trigger.name}
                        </div>
                        <div className="frost-text-muted text-xs capitalize">{trigger.provider}</div>
                      </TableCell>
                      <TableCell className="max-w-[180px] truncate text-sm" title={mailbox}>
                        {mailbox}
                      </TableCell>
                      <TableCell className="max-w-[180px]">
                        <div className="truncate text-sm" title={entityName}>
                          {entityName}
                        </div>
                        <div className="frost-text-muted text-xs capitalize">{trigger.entity_type}</div>
                      </TableCell>
                      <TableCell className="max-w-[160px] truncate font-mono text-xs" title={subjectRegex || undefined}>
                        {subjectRegex || 'All subjects'}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{formatDateTime(trigger.updated_at)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          {canPauseResume ? (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={isActing(trigger.id)}
                              onClick={() => void handlePauseResume(trigger)}
                            >
                              {trigger.status === 'paused' ? 'Resume' : 'Pause'}
                            </Button>
                          ) : null}
                          {canRetry ? (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={isActing(trigger.id)}
                              onClick={() => void handleRetry(trigger)}
                            >
                              Retry
                            </Button>
                          ) : null}
                          <Button variant="destructive" size="sm" onClick={() => deletion.ask(trigger)}>
                            Delete
                          </Button>
                        </div>
                        {trigger.last_error ? (
                          <p className="mt-1 max-w-[240px] truncate text-xs text-red-500" title={trigger.last_error}>
                            {trigger.last_error}
                          </p>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {appId ? <CreateTriggerDialog isOpen={formOpen} appId={appId} onOpenChange={setFormOpen} /> : null}

      {deletion.item ? (
        <DeleteConfirmationDialog
          {...deletion.dialogProps}
          title="Delete trigger"
          message="Are you sure you want to delete this trigger? The Gmail watch will be stopped. The email connection will not be removed."
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      ) : null}
    </div>
  );
};

export default TriggersPage;
