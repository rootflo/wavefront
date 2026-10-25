import MultiSelect from '@app/components/MultiSelect';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { EMAIL_CONTENT_PLACEHOLDER } from '@app/constants/scheduled-job';
import { formatUserLabel, normalizeUserId } from './scheduled-job-utils';
import { getUserId, getUserSearchValue, selectedUsersCountLabel } from './scheduled-job-form';
import { ScheduledJobFormState } from './useScheduledJobForm';

/** Who receives the results, which mailbox sends them, and the message around them. */
const EmailTab = ({ form }: { form: ScheduledJobFormState }) => {
  const {
    appUsers,
    appUsersLoading,
    selectedRecipientUserIds,
    setSelectedRecipientUserIds,
    emailConnectionId,
    subject,
    setSubject,
    emailContent,
    setEmailContent,
    sendableConnections,
    handleSenderChange,
  } = form;
  return (
    <>
      <div>
        <p className="frost-text-muted mb-1 text-xs">Subject (optional)</p>
        <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Daily report" />
      </div>

      <div>
        <p className="frost-text-muted mb-1 text-xs">Send from</p>
        <Select value={emailConnectionId || undefined} onValueChange={handleSenderChange}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select a mailbox" />
          </SelectTrigger>
          <SelectContent>
            {sendableConnections.map((connection) => (
              <SelectItem key={connection.id} value={connection.id}>
                {connection.name} ({connection.mailbox_email})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <p className="frost-text-muted mb-1 text-xs">Email content (optional)</p>
        <Textarea
          value={emailContent}
          onChange={(e) => setEmailContent(e.target.value)}
          placeholder={EMAIL_CONTENT_PLACEHOLDER}
          className="min-h-[120px]"
        />
      </div>

      <div>
        <p className="frost-text-muted mb-1 text-xs">Recipient users</p>
        <MultiSelect
          items={appUsers}
          selectedIds={selectedRecipientUserIds}
          onChange={setSelectedRecipientUserIds}
          getId={getUserId}
          getLabel={formatUserLabel}
          getSearchValue={getUserSearchValue}
          normalizeId={normalizeUserId}
          placeholder="Select recipient users"
          searchPlaceholder="Search users..."
          loading={appUsersLoading}
          loadingLabel="Loading users..."
          emptyLabel="No users found."
          showSelectAll
          selectedGroupHeading="Selected"
          allItemsGroupHeading="All users"
          selectedCountLabel={selectedUsersCountLabel}
        />
      </div>
    </>
  );
};

export default EmailTab;
