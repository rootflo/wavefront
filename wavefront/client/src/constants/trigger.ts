import { TriggerEntityType, TriggerProvider, TriggerStatus } from '@app/types/trigger';

export const TRIGGER_PROVIDER_GMAIL: TriggerProvider = 'gmail';

export const TRIGGER_ENTITY_TYPES: { value: TriggerEntityType; label: string }[] = [
  { value: 'agent', label: 'Agent' },
  { value: 'workflow', label: 'Workflow' },
];

export const TRIGGER_STATUS_OPTIONS: { value: TriggerStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'pending_auth', label: 'Pending auth' },
  { value: 'error', label: 'Error' },
];

/** Mirrors server DEFAULT_ALLOWED_MIME_TYPES in triggers input_builder. */
export const TRIGGER_MIME_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'application/pdf', label: 'PDF' },
  { value: 'text/plain', label: 'Plain text' },
  { value: 'text/csv', label: 'CSV' },
  {
    value: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    label: 'Word (.docx)',
  },
  {
    value: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    label: 'Excel (.xlsx)',
  },
  { value: 'image/png', label: 'PNG' },
  { value: 'image/jpeg', label: 'JPEG' },
  { value: 'image/jpg', label: 'JPG' },
];

export const TRIGGER_STATUS_BADGE_CLASS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  paused: 'bg-yellow-100 text-yellow-800',
  pending_auth: 'bg-blue-100 text-blue-800',
  error: 'bg-red-100 text-red-800',
  deleted: 'bg-gray-100 text-gray-800',
};
