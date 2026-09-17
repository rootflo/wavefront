import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
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
import { TRIGGER_ENTITY_TYPES, TRIGGER_MIME_TYPE_OPTIONS, TRIGGER_PROVIDER_GMAIL } from '@app/constants/trigger';
import { useGetAgents, useGetEmailConnections, useGetWorkflows } from '@app/hooks';
import { cn } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { TriggerEntityType } from '@app/types/trigger';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';

interface CreateTriggerDialogProps {
  isOpen: boolean;
  appId: string;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

const CreateTriggerDialog: React.FC<CreateTriggerDialogProps> = ({ isOpen, appId, onOpenChange, onSuccess }) => {
  const { notifySuccess } = useNotifyStore();
  const { data: emailConnections = [] } = useGetEmailConnections(appId);
  const { data: agents = [], isLoading: agentsLoading } = useGetAgents(appId);
  const { data: workflows = [], isLoading: workflowsLoading } = useGetWorkflows(appId);

  const [name, setName] = useState('');
  const [connectionId, setConnectionId] = useState('');
  const [entityType, setEntityType] = useState<TriggerEntityType>('agent');
  const [entityId, setEntityId] = useState('');
  const [namespace, setNamespace] = useState('');
  const [subjectRegex, setSubjectRegex] = useState('');
  const [selectedMimeTypes, setSelectedMimeTypes] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const readableConnections = useMemo(
    () =>
      emailConnections.filter(
        (connection) => connection.status === 'active' && connection.provider === TRIGGER_PROVIDER_GMAIL
      ),
    [emailConnections]
  );

  const entityOptions = entityType === 'agent' ? agents : workflows;
  const entitiesLoading = entityType === 'agent' ? agentsLoading : workflowsLoading;

  const resetForm = () => {
    setName('');
    setConnectionId('');
    setEntityType('agent');
    setEntityId('');
    setNamespace('');
    setSubjectRegex('');
    setSelectedMimeTypes([]);
    setError('');
  };

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen]);

  const handleOpenChange = (open: boolean) => {
    if (!open && !saving) {
      resetForm();
    }
    onOpenChange(open);
  };

  const handleEntityTypeChange = (value: string) => {
    if (value !== 'agent' && value !== 'workflow') return;
    setEntityType(value);
    setEntityId('');
  };

  const toggleMimeType = (mimeType: string) => {
    setSelectedMimeTypes((prev) =>
      prev.includes(mimeType) ? prev.filter((value) => value !== mimeType) : [...prev, mimeType]
    );
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!connectionId) {
      setError('Select an active Gmail connection to watch');
      return;
    }
    if (!entityId) {
      setError(`Select a ${entityType} to run when mail arrives`);
      return;
    }

    setSaving(true);
    setError('');
    try {
      await floConsoleService.triggerService.createTrigger({
        name: name.trim(),
        provider: TRIGGER_PROVIDER_GMAIL,
        entity_type: entityType,
        entity_id: entityId,
        connection_id: connectionId,
        namespace: namespace.trim() || null,
        filter_config: {
          subject_regex: subjectRegex.trim() || null,
          allowed_mime_types: selectedMimeTypes.length > 0 ? selectedMimeTypes : null,
        },
      });
      notifySuccess('Trigger created successfully');
      onSuccess();
      handleOpenChange(false);
    } catch {
      setError('Unable to create trigger. Confirm the mailbox is authorized for read access and try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create Trigger</DialogTitle>
          <DialogDescription>
            Watch a connected Gmail inbox and run an agent or workflow when matching mail arrives.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div>
            <p className="mb-1 text-xs text-[#878787]">Name</p>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Invoice intake" />
          </div>

          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <p className="text-xs text-[#878787]">Mailbox to watch</p>
            </div>
            {readableConnections.length === 0 ? (
              <p className="text-sm text-[#878787]">
                No active Gmail connections.{' '}
                <Link to={`/apps/${appId}/email-connections`} className="hover:text-foreground underline">
                  Connect a mailbox
                </Link>
              </p>
            ) : (
              <Select value={connectionId || undefined} onValueChange={setConnectionId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a mailbox" />
                </SelectTrigger>
                <SelectContent>
                  {readableConnections.map((connection) => (
                    <SelectItem key={connection.id} value={connection.id}>
                      {connection.name} ({connection.mailbox_email})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Run</p>
              <Select value={entityType} onValueChange={handleEntityTypeChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TRIGGER_ENTITY_TYPES.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">{entityType === 'agent' ? 'Agent' : 'Workflow'}</p>
              <Select value={entityId || undefined} onValueChange={setEntityId} disabled={entitiesLoading}>
                <SelectTrigger>
                  <SelectValue placeholder={entitiesLoading ? 'Loading...' : `Select ${entityType}`} />
                </SelectTrigger>
                <SelectContent>
                  {entityOptions.map((entity) => (
                    <SelectItem key={entity.id} value={entity.id}>
                      {entity.name}
                      {entity.namespace ? ` (${entity.namespace})` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <p className="text-xs text-[#878787]">Namespace (optional)</p>
            </div>
            <Input value={namespace} onChange={(e) => setNamespace(e.target.value)} placeholder="production" />
          </div>

          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <p className="text-xs text-[#878787]">Subject regex (optional)</p>
            </div>
            <Input
              value={subjectRegex}
              onChange={(e) => setSubjectRegex(e.target.value)}
              placeholder="Invoice.*"
              className="font-mono"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <p className="text-xs text-[#878787]">Allowed attachment types (optional)</p>
            </div>
            <div className="frost-glass border-frost-border flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded-md border p-3">
              {TRIGGER_MIME_TYPE_OPTIONS.map((option) => {
                const isSelected = selectedMimeTypes.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => toggleMimeType(option.value)}
                    className={cn(
                      'rounded-full border px-3 py-1 text-xs transition-colors',
                      isSelected
                        ? 'border-frost-text bg-frost-text text-white dark:bg-white dark:text-slate-900'
                        : 'frost-glass-strong frost-text border-frost-border hover:border-frost-text'
                    )}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {error ? <p className="text-sm text-red-500">{error}</p> : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => void handleSave()} loading={saving} disabled={saving}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTriggerDialog;
