import { FormInputField, FormSelectField, FormTextareaField } from '@app/components/FormFields';
import MultiSelect from '@app/components/MultiSelect';
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { EMAIL_CONTENT_PLACEHOLDER } from '@app/constants/scheduled-job';
import { FIELD_STYLE, getUserId, getUserSearchValue, selectedUsersCountLabel } from './scheduled-job-form';
import { formatUserLabel, normalizeUserId } from './scheduled-job-utils';
import { ScheduledJobFormState } from './useScheduledJobForm';

/** Who receives the results, which mailbox sends them, and the message around them. */
const EmailTab = ({ state }: { state: ScheduledJobFormState }) => {
  const { form, appUsers, appUsersLoading, sendableConnections } = state;
  const { control } = form;
  return (
    <>
      <FormInputField
        {...FIELD_STYLE}
        control={control}
        name="subject"
        label="Subject (optional)"
        placeholder="Daily report"
      />

      <FormSelectField
        {...FIELD_STYLE}
        control={control}
        name="emailConnectionId"
        label="Send from"
        placeholder="Select a mailbox"
        options={sendableConnections.map((connection) => ({
          value: connection.id,
          label: `${connection.name} (${connection.mailbox_email})`,
        }))}
      />

      <FormTextareaField
        {...FIELD_STYLE}
        control={control}
        name="emailContent"
        label="Email content (optional)"
        placeholder={EMAIL_CONTENT_PLACEHOLDER}
        className="space-y-1 [&_textarea]:min-h-[120px]"
      />

      <FormField
        control={control}
        name="recipientUserIds"
        render={({ field }) => (
          <FormItem className={FIELD_STYLE.className}>
            <FormLabel className={FIELD_STYLE.labelClassName}>Recipient users</FormLabel>
            <FormControl>
              <MultiSelect
                items={appUsers}
                selectedIds={field.value}
                onChange={field.onChange}
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
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
};

export default EmailTab;
