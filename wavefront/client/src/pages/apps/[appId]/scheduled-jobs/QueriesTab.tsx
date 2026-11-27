import { FormInputField, FormSelectField, FormTextareaField } from '@app/components/FormFields';
import { Button } from '@wavefront/ui/button';
import { COLUMN_STYLES_PLACEHOLDER, QUERY_PARAMS_PLACEHOLDER } from '@app/constants/scheduled-job';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useWatch } from 'react-hook-form';
import DateRangeFields from './DateRangeFields';
import { FIELD_STYLE, QueryEntryValues, createEmptyQueryEntry } from './scheduled-job-form';
import { ScheduledJobFormState } from './useScheduledJobForm';

const INHERIT = '__inherit__';
const JSON_TEXTAREA = 'space-y-1 [&_textarea]:min-h-20 [&_textarea]:font-mono [&_textarea]:text-xs';

interface QueryCardProps {
  state: ScheduledJobFormState;
  index: number;
  queries: QueryEntryValues[];
}

/** One query entry: which query to run, and optional overrides of the job defaults. */
const QueryCard = ({ state, index, queries }: QueryCardProps) => {
  const { form, queryFields, isEmailJob, datasources, availableQueryIds } = state;
  const { control } = form;
  const queryId = queries[index]?.queryId ?? '';
  // New (empty) entries open so a query can be picked; loaded ones start collapsed.
  const [expanded, setExpanded] = useState(!queryId);
  const hasError = Boolean(form.formState.errors.queries?.[index]);
  const isOpen = expanded || hasError;
  const title = queryId || `Query ${index + 1}`;
  // Each query can be added once: offer this entry's own query plus the unused ones.
  const usedByOthers = new Set(queries.filter((_, i) => i !== index).map((query) => query.queryId));
  const queryOptions = availableQueryIds
    .filter((id) => id === queryId || !usedByOthers.has(id))
    .map((id) => ({ value: id, label: id }));

  return (
    <div className="border-frost-border overflow-hidden rounded-md border">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
          onClick={() => setExpanded(!isOpen)}
          aria-expanded={isOpen}
        >
          <ChevronDown
            className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${isOpen ? 'rotate-0' : '-rotate-90'}`}
          />
          <span className="frost-text truncate text-sm font-medium">{title}</span>
          {!queryId ? <span className="frost-text-muted shrink-0 text-xs">Select a query</span> : null}
        </button>
        <button
          type="button"
          className="frost-text-muted rounded-md p-1.5 transition-colors hover:text-red-500"
          aria-label={`Remove ${title}`}
          onClick={() => queryFields.remove(index)}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {isOpen ? (
        <div className="border-frost-border space-y-3 border-t px-4 py-4">
          <FormSelectField
            {...FIELD_STYLE}
            control={control}
            name={`queries.${index}.queryId`}
            label="Query"
            placeholder="Select a query"
            options={queryOptions}
          />

          <FormSelectField
            {...FIELD_STYLE}
            control={control}
            name={`queries.${index}.overrides.datasourceId`}
            label="Datasource override (optional)"
            emptyOption={{ value: INHERIT, label: 'Inherit job datasource' }}
            options={datasources.map((ds) => ({ value: ds.id, label: ds.name || ds.id }))}
          />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormInputField
              {...FIELD_STYLE}
              control={control}
              name={`queries.${index}.overrides.limit`}
              label="Row limit override"
              placeholder="Inherit"
            />
            <FormInputField
              {...FIELD_STYLE}
              control={control}
              name={`queries.${index}.overrides.offset`}
              label="Offset override"
              placeholder="Inherit"
            />
          </div>

          <FormInputField
            {...FIELD_STYLE}
            control={control}
            name={`queries.${index}.overrides.filter`}
            label="Filter override (optional)"
            placeholder="Inherit"
          />

          <DateRangeFields control={control} prefix={`queries.${index}.overrides`} />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormTextareaField
              {...FIELD_STYLE}
              control={control}
              name={`queries.${index}.overrides.paramsJson`}
              label="Params override (optional JSON)"
              placeholder={QUERY_PARAMS_PLACEHOLDER}
              className={JSON_TEXTAREA}
            />
            {isEmailJob ? (
              <FormTextareaField
                {...FIELD_STYLE}
                control={control}
                name={`queries.${index}.overrides.columnStylesJson`}
                label="Column styles override (optional JSON)"
                placeholder={COLUMN_STYLES_PLACEHOLDER}
                className={JSON_TEXTAREA}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

/** The dynamic queries the job runs, each with optional overrides of the job's defaults. */
const QueriesTab = ({ state }: { state: ScheduledJobFormState }) => {
  const { form, queryFields, availableQueryIds, dynamicQueriesLoading } = state;
  const [datasourceId, queries] = useWatch({ control: form.control, name: ['datasourceId', 'queries'] });
  const listError = form.formState.errors.queries?.root?.message ?? form.formState.errors.queries?.message;
  const canAdd = queryFields.fields.length < availableQueryIds.length;
  const addQuery = () => queryFields.append(createEmptyQueryEntry());

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="frost-text text-sm font-medium">Query configurations</p>
          <p className="frost-text-muted text-xs">
            Add a query, then optionally override job-level defaults. Leave fields empty to inherit.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addQuery}
          disabled={!datasourceId || dynamicQueriesLoading || !canAdd}
        >
          <Plus className="mr-1 h-4 w-4" />
          Add query
        </Button>
      </div>

      {listError ? <p className="text-destructive text-[0.8rem] font-medium">{listError}</p> : null}

      {!datasourceId ? (
        <p className="frost-text-muted text-sm">Select a datasource on the Job setup tab to load queries.</p>
      ) : dynamicQueriesLoading ? (
        <p className="frost-text-muted text-sm">Loading queries...</p>
      ) : availableQueryIds.length === 0 ? (
        <p className="frost-text-muted text-sm">No dynamic queries found for this datasource.</p>
      ) : queryFields.fields.length === 0 ? (
        <button
          type="button"
          onClick={addQuery}
          className="border-frost-border frost-text-muted hover:frost-text hover:bg-frost-glass-strong flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-4 py-8 text-sm transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add your first query configuration
        </button>
      ) : (
        <div className="space-y-3">
          {queryFields.fields.map((field, index) => (
            <QueryCard key={field.id} state={state} index={index} queries={queries} />
          ))}

          <button
            type="button"
            onClick={addQuery}
            disabled={!canAdd}
            className="border-frost-border frost-text-muted hover:frost-text hover:bg-frost-glass-strong flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-3 py-3 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Plus className="h-4 w-4" />
            Add another query
          </button>
        </div>
      )}
    </>
  );
};

export default QueriesTab;
