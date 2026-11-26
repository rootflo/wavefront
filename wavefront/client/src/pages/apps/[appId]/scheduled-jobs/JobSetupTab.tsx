import { FormInputField, FormSelectField, FormTextareaField } from '@app/components/FormFields';
import {
  COLUMN_STYLES_PLACEHOLDER,
  DEFAULT_CRON_EXPR,
  DEFAULT_MAX_RETRIES,
  DEFAULT_QUERY_LIMIT,
  DEFAULT_QUERY_OFFSET,
  DEFAULT_TIMEZONE,
  FILTER_PLACEHOLDER,
  JOB_TYPE_EMAIL_DYNAMIC_QUERY,
  JOB_TYPE_LABELS,
  JOB_TYPE_SCHEDULED_QUERY,
  QUERY_PARAMS_PLACEHOLDER,
} from '@app/constants/scheduled-job';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useWatch } from 'react-hook-form';
import DateRangeFields from './DateRangeFields';
import { FIELD_STYLE } from './scheduled-job-form';
import { ScheduledJobFormState } from './useScheduledJobForm';

const JOB_TYPE_OPTIONS = [JOB_TYPE_EMAIL_DYNAMIC_QUERY, JOB_TYPE_SCHEDULED_QUERY].map((value) => ({
  value,
  label: JOB_TYPE_LABELS[value],
}));

/** What the job does, how often it runs, from which datasource, and the defaults its queries share. */
const JobSetupTab = ({ state }: { state: ScheduledJobFormState }) => {
  const { form, queryFields, isEditing, isEmailJob, datasources } = state;
  const { control } = form;
  // The query rows were all picked under this datasource: changing it clears them.
  const [datasourceId, queries] = useWatch({ control, name: ['datasourceId', 'queries'] });
  const selectedQueryIds = queries.map((query) => query.queryId).filter(Boolean);
  const [defaultsExpanded, setDefaultsExpanded] = useState(false);
  // Keep the section open while it holds an error, so the message is visible.
  const showDefaults = defaultsExpanded || Boolean(form.formState.errors.defaults);

  return (
    <>
      <FormSelectField
        {...FIELD_STYLE}
        control={control}
        name="jobType"
        label="Job type"
        options={JOB_TYPE_OPTIONS}
        disabled={isEditing}
        description={
          <>
            {isEmailJob
              ? 'Runs the queries and emails the results to the recipients.'
              : 'Runs the queries on schedule and discards the results. Nothing is emailed.'}
            {isEditing ? ' The job type cannot be changed after creation.' : ''}
          </>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormInputField
          {...FIELD_STYLE}
          control={control}
          name="cronExpr"
          label="Cron expression"
          placeholder={DEFAULT_CRON_EXPR}
        />
        <FormInputField
          {...FIELD_STYLE}
          control={control}
          name="timezone"
          label="Timezone"
          placeholder={DEFAULT_TIMEZONE}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormSelectField
          {...FIELD_STYLE}
          control={control}
          name="datasourceId"
          label="Datasource"
          placeholder="Select datasource"
          options={datasources.map((ds) => ({ value: ds.id, label: ds.name || ds.id }))}
          onValueChange={(value) => {
            // `datasourceId` is still the value the rows were picked under (this render's value).
            if (value !== datasourceId) queryFields.replace([]);
          }}
        />
        <FormInputField
          {...FIELD_STYLE}
          control={control}
          name="maxRetries"
          label="Max retries"
          placeholder={DEFAULT_MAX_RETRIES}
        />
      </div>

      <div>
        <p className="frost-text-muted mb-2 text-xs">Selected queries</p>
        {selectedQueryIds.length === 0 ? (
          <p className="frost-text-muted text-sm">No queries selected yet. Choose them on the Query tab.</p>
        ) : (
          <div className="frost-glass border-frost-border flex max-h-28 flex-wrap gap-2 overflow-y-auto rounded-md border p-3">
            {selectedQueryIds.map((queryId) => (
              <span
                key={queryId}
                className="frost-glass-strong frost-text border-frost-border rounded-full border px-3 py-1 text-xs"
              >
                {queryId}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="border-frost-border overflow-hidden rounded-md border">
        <button
          type="button"
          className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left"
          onClick={() => setDefaultsExpanded((prev) => !prev)}
          aria-expanded={showDefaults}
        >
          <ChevronDown
            className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${showDefaults ? 'rotate-0' : '-rotate-90'}`}
          />
          <div className="min-w-0">
            <p className="frost-text truncate text-sm font-medium">Job-level query defaults</p>
            <p className="frost-text-muted truncate text-xs">
              Applied to every selected query unless overridden on the Query tab.
            </p>
          </div>
        </button>

        {showDefaults ? (
          <div className="border-frost-border space-y-4 border-t px-4 py-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <FormInputField
                {...FIELD_STYLE}
                control={control}
                name="defaults.limit"
                label="Row limit"
                placeholder={DEFAULT_QUERY_LIMIT}
              />
              <FormInputField
                {...FIELD_STYLE}
                control={control}
                name="defaults.offset"
                label="Offset"
                placeholder={DEFAULT_QUERY_OFFSET}
              />
            </div>

            <FormInputField
              {...FIELD_STYLE}
              control={control}
              name="defaults.filter"
              label="Filter expression (optional)"
              placeholder={FILTER_PLACEHOLDER}
            />

            <DateRangeFields control={control} prefix="defaults" />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <FormTextareaField
                {...FIELD_STYLE}
                control={control}
                name="defaults.paramsJson"
                label="Query params (optional JSON)"
                placeholder={QUERY_PARAMS_PLACEHOLDER}
                className="space-y-1 [&_textarea]:min-h-[90px] [&_textarea]:font-mono"
              />
              {isEmailJob ? (
                <FormTextareaField
                  {...FIELD_STYLE}
                  control={control}
                  name="defaults.columnStylesJson"
                  label="Column styles (optional JSON)"
                  placeholder={COLUMN_STYLES_PLACEHOLDER}
                  className="space-y-1 [&_textarea]:min-h-[90px] [&_textarea]:font-mono [&_textarea]:text-xs"
                />
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
};

export default JobSetupTab;
