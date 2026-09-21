import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Badge } from '@app/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { TRIGGER_STATUS_BADGE_CLASS, TRIGGER_STATUS_OPTIONS } from '@app/constants/trigger';
import { useGetAgents, useGetEmailConnections, useGetTriggers, useGetWorkflows } from '@app/hooks';
import { getTriggersKey } from '@app/hooks/data/query-keys';
import { cn } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { Trigger } from '@app/types/trigger';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateTriggerDialog from './CreateTriggerDialog';

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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedApp } = useDashboardStore();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [deleteTrigger, setDeleteTrigger] = useState<Trigger | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [actionTriggerId, setActionTriggerId] = useState<string | null>(null);

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
      const subjectRegex = getSubjectRegex(trigger) || '';
      return (
        trigger.name.toLowerCase().includes(term) ||
        trigger.provider.toLowerCase().includes(term) ||
        trigger.status.toLowerCase().includes(term) ||
        trigger.entity_type.toLowerCase().includes(term) ||
        entityName.toLowerCase().includes(term) ||
        mailbox.toLowerCase().includes(term) ||
        (trigger.namespace || '').toLowerCase().includes(term) ||
        subjectRegex.toLowerCase().includes(term)
      );
    });
  }, [triggers, searchTerm, statusFilter, connectionLabelById, entityLabelById]);

  const refreshTriggers = () => {
    queryClient.invalidateQueries({ queryKey: getTriggersKey(appId || '') });
  };

  const handlePauseResume = async (trigger: Trigger) => {
    setActionTriggerId(trigger.id);
    try {
      if (trigger.status === 'paused') {
        await floConsoleService.triggerService.resumeTrigger(trigger.id);
        notifySuccess('Trigger resumed');
      } else {
        await floConsoleService.triggerService.pauseTrigger(trigger.id);
        notifySuccess('Trigger paused');
      }
      refreshTriggers();
    } catch {
      notifyError('Failed to update trigger status');
    } finally {
      setActionTriggerId(null);
    }
  };

  const handleRetry = async (trigger: Trigger) => {
    setActionTriggerId(trigger.id);
    try {
      await floConsoleService.triggerService.retryTrigger(trigger.id);
      notifySuccess('Watch registration retried');
      refreshTriggers();
    } catch {
      notifyError('Failed to retry trigger');
    } finally {
      setActionTriggerId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTrigger) return;
    setDeleting(true);
    try {
      await floConsoleService.triggerService.deleteTrigger(deleteTrigger.id);
      notifySuccess('Trigger deleted');
      setDeleteTrigger(null);
      refreshTriggers();
    } catch {
      notifyError('Failed to delete trigger');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-8">
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
                onClick={() => navigate(`/apps/${appId}/triggers`)}
                className="hover:text-foreground cursor-pointer"
              >
                Triggers
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full shrink-0 items-start justify-between">
        <div>
          <h1 className="frost-text text-3xl font-bold">Triggers</h1>
          <p className="frost-text-muted mt-2">
            Run agents and workflows from inbound email for {selectedApp?.app_name}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Input
            className="w-[200px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              {TRIGGER_STATUS_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={() => setFormOpen(true)}>Create Trigger</Button>
        </div>
      </div>

      {isLoading ? (
        <p className="frost-text-muted text-sm">Loading triggers...</p>
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
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
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
                      <div className="text-xs text-[#878787] capitalize">{trigger.provider}</div>
                    </TableCell>
                    <TableCell className="max-w-[180px] truncate text-sm" title={mailbox}>
                      {mailbox}
                    </TableCell>
                    <TableCell className="max-w-[180px]">
                      <div className="truncate text-sm" title={entityName}>
                        {entityName}
                      </div>
                      <div className="text-xs text-[#878787] capitalize">{trigger.entity_type}</div>
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
                            disabled={actionTriggerId === trigger.id}
                            onClick={() => void handlePauseResume(trigger)}
                          >
                            {trigger.status === 'paused' ? 'Resume' : 'Pause'}
                          </Button>
                        ) : null}
                        {canRetry ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={actionTriggerId === trigger.id}
                            onClick={() => void handleRetry(trigger)}
                          >
                            Retry
                          </Button>
                        ) : null}
                        <Button variant="destructive" size="sm" onClick={() => setDeleteTrigger(trigger)}>
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
      )}

      {appId ? (
        <CreateTriggerDialog isOpen={formOpen} appId={appId} onOpenChange={setFormOpen} onSuccess={refreshTriggers} />
      ) : null}

      {deleteTrigger ? (
        <DeleteConfirmationDialog
          isOpen={Boolean(deleteTrigger)}
          title="Delete trigger"
          message="Are you sure you want to delete this trigger? The Gmail watch will be stopped. The email connection will not be removed."
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTrigger(null)}
          loading={deleting}
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      ) : null}
    </div>
  );
};

export default TriggersPage;
