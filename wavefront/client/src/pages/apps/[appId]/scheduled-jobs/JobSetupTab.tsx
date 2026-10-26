import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import {
  COLUMN_STYLES_PLACEHOLDER,
  DEFAULT_CRON_EXPR,
  DEFAULT_MAX_RETRIES,
  DEFAULT_QUERY_LIMIT,
  DEFAULT_QUERY_OFFSET,
  DEFAULT_TIMEZONE,
  FILTER_PLACEHOLDER,
  QUERY_PARAMS_PLACEHOLDER,
} from '@app/constants/scheduled-job';
import { ChevronDown } from 'lucide-react';
import { getDatasourceIdFromPayload } from './scheduled-job-utils';
import { ScheduledJobFormState } from './useScheduledJobForm';
import DateRangeFields from './DateRangeFields';

/** How often the job runs, from which datasource, and the defaults its queries share. */
const JobSetupTab = ({ form }: { form: ScheduledJobFormState }) => {
  const {
    job,
    datasources,
    datasourceId,
    setDatasourceId,
    setQueryConfigs,
    setExpandedQueryKeys,
    jobDefaultsExpanded,
    setJobDefaultsExpanded,
    cronExpr,
    setCronExpr,
    timezone,
    setTimezone,
    queryParamsJson,
    setQueryParamsJson,
    columnStylesJson,
    setColumnStylesJson,
    filterExpr,
    setFilterExpr,
    queryLimit,
    setQueryLimit,
    queryOffset,
    setQueryOffset,
    dateRange,
    setDateRange,
    startDateParamKey,
    setStartDateParamKey,
    endDateParamKey,
    setEndDateParamKey,
    maxRetries,
    setMaxRetries,
    selectedQueryIds,
  } = form;
  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <p className="frost-text-muted mb-1 text-xs">Cron expression</p>
          <Input value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder={DEFAULT_CRON_EXPR} />
        </div>
        <div>
          <p className="frost-text-muted mb-1 text-xs">Timezone</p>
          <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder={DEFAULT_TIMEZONE} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <p className="frost-text-muted mb-1 text-xs">Datasource</p>
          <Select
            value={datasourceId}
            onValueChange={(value) => {
              setDatasourceId(value);
              if (!job || getDatasourceIdFromPayload(job.payload || {}) !== value) {
                setQueryConfigs([]);
                setExpandedQueryKeys(new Set());
              }
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select datasource" />
            </SelectTrigger>
            <SelectContent>
              {datasources.map((ds) => (
                <SelectItem key={ds.id} value={ds.id}>
                  {ds.name || ds.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="frost-text-muted mb-1 text-xs">Max retries</p>
          <Input value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} placeholder={DEFAULT_MAX_RETRIES} />
        </div>
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
          onClick={() => setJobDefaultsExpanded((prev) => !prev)}
          aria-expanded={jobDefaultsExpanded}
        >
          <ChevronDown
            className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${jobDefaultsExpanded ? 'rotate-0' : '-rotate-90'}`}
          />
          <div className="min-w-0">
            <p className="frost-text truncate text-sm font-medium">Job-level query defaults</p>
            <p className="frost-text-muted truncate text-xs">
              Applied to every selected query unless overridden on the Query tab.
            </p>
          </div>
        </button>

        {jobDefaultsExpanded ? (
          <div className="border-frost-border space-y-4 border-t px-4 py-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <p className="frost-text-muted mb-1 text-xs">Row limit</p>
                <Input
                  value={queryLimit}
                  onChange={(e) => setQueryLimit(e.target.value)}
                  placeholder={DEFAULT_QUERY_LIMIT}
                />
              </div>
              <div>
                <p className="frost-text-muted mb-1 text-xs">Offset</p>
                <Input
                  value={queryOffset}
                  onChange={(e) => setQueryOffset(e.target.value)}
                  placeholder={DEFAULT_QUERY_OFFSET}
                />
              </div>
            </div>

            <div>
              <p className="frost-text-muted mb-1 text-xs">Filter expression (optional)</p>
              <Input
                value={filterExpr}
                onChange={(e) => setFilterExpr(e.target.value)}
                placeholder={FILTER_PLACEHOLDER}
              />
            </div>

            <DateRangeFields
              value={dateRange}
              onDateRangeChange={setDateRange}
              startKey={startDateParamKey}
              onStartKeyChange={setStartDateParamKey}
              endKey={endDateParamKey}
              onEndKeyChange={setEndDateParamKey}
            />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <p className="frost-text-muted mb-1 text-xs">Query params (optional JSON)</p>
                <Textarea
                  value={queryParamsJson}
                  onChange={(e) => setQueryParamsJson(e.target.value)}
                  placeholder={QUERY_PARAMS_PLACEHOLDER}
                  className="min-h-[90px] font-mono"
                />
              </div>
              <div>
                <p className="frost-text-muted mb-1 text-xs">Column styles (optional JSON)</p>
                <Textarea
                  value={columnStylesJson}
                  onChange={(e) => setColumnStylesJson(e.target.value)}
                  placeholder={COLUMN_STYLES_PLACEHOLDER}
                  className="min-h-[90px] font-mono text-xs"
                />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
};

export default JobSetupTab;
