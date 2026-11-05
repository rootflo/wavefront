import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import {
  COLUMN_STYLES_PLACEHOLDER,
  DATE_RANGE,
  DEFAULT_END_DATE_PARAM,
  DEFAULT_START_DATE_PARAM,
  QUERY_PARAMS_PLACEHOLDER,
} from '@app/constants/scheduled-job';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import { ScheduledJobFormState } from './useScheduledJobForm';
import DateRangeFields from './DateRangeFields';

/** The dynamic queries the job runs, each with optional overrides of the job's defaults. */
const QueriesTab = ({ form }: { form: ScheduledJobFormState }) => {
  const {
    datasources,
    datasourceId,
    queryConfigs,
    expandedQueryKeys,
    dynamicQueriesLoading,
    availableQueryIds,
    updateQueryConfig,
    updateQueryConfigOverrides,
    toggleQueryExpanded,
    addQueryConfig,
    removeQueryConfig,
    queryOptionsForConfig,
  } = form;
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
          onClick={addQueryConfig}
          disabled={
            !datasourceId ||
            dynamicQueriesLoading ||
            availableQueryIds.length === 0 ||
            queryConfigs.length >= availableQueryIds.length
          }
        >
          <Plus className="mr-1 h-4 w-4" />
          Add query
        </Button>
      </div>

      {!datasourceId ? (
        <p className="frost-text-muted text-sm">Select a datasource on the Job setup tab to load queries.</p>
      ) : dynamicQueriesLoading ? (
        <p className="frost-text-muted text-sm">Loading queries...</p>
      ) : availableQueryIds.length === 0 ? (
        <p className="frost-text-muted text-sm">No dynamic queries found for this datasource.</p>
      ) : queryConfigs.length === 0 ? (
        <button
          type="button"
          onClick={addQueryConfig}
          className="border-frost-border frost-text-muted hover:frost-text hover:bg-frost-glass-strong flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-4 py-8 text-sm transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add your first query configuration
        </button>
      ) : (
        <div className="space-y-3">
          {queryConfigs.map((config, index) => {
            const isExpanded = expandedQueryKeys.has(config.key);
            const overrides = config.overrides;
            const title = config.queryId || `Query ${index + 1}`;
            const queryOptions = queryOptionsForConfig(config.key, config.queryId);

            return (
              <div key={config.key} className="border-frost-border overflow-hidden rounded-md border">
                <div className="flex items-center gap-2 px-3 py-2">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
                    onClick={() => toggleQueryExpanded(config.key)}
                    aria-expanded={isExpanded}
                  >
                    <ChevronDown
                      className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${isExpanded ? 'rotate-0' : '-rotate-90'}`}
                    />
                    <span className="frost-text truncate text-sm font-medium">{title}</span>
                    {!config.queryId ? <span className="frost-text-muted shrink-0 text-xs">Select a query</span> : null}
                  </button>
                  <button
                    type="button"
                    className="frost-text-muted rounded-md p-1.5 transition-colors hover:text-red-500"
                    aria-label={`Remove ${title}`}
                    onClick={() => removeQueryConfig(config.key)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                {isExpanded ? (
                  <div className="border-frost-border space-y-3 border-t px-4 py-4">
                    <div>
                      <p className="frost-text-muted mb-1 text-xs">Query</p>
                      <Select
                        value={config.queryId || undefined}
                        onValueChange={(value) => updateQueryConfig(config.key, { queryId: value })}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select a query" />
                        </SelectTrigger>
                        <SelectContent>
                          {queryOptions.map((queryId) => (
                            <SelectItem key={queryId} value={queryId}>
                              {queryId}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <p className="frost-text-muted mb-1 text-xs">Datasource override (optional)</p>
                      <Select
                        value={overrides.datasource_id || '__inherit__'}
                        onValueChange={(value) =>
                          updateQueryConfigOverrides(config.key, {
                            datasource_id: value === '__inherit__' ? '' : value,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Inherit job datasource" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__inherit__">Inherit job datasource</SelectItem>
                          {datasources.map((ds) => (
                            <SelectItem key={ds.id} value={ds.id}>
                              {ds.name || ds.id}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <p className="frost-text-muted mb-1 text-xs">Row limit override</p>
                        <Input
                          value={overrides.limit ?? ''}
                          onChange={(e) => updateQueryConfigOverrides(config.key, { limit: e.target.value })}
                          placeholder="Inherit"
                        />
                      </div>
                      <div>
                        <p className="frost-text-muted mb-1 text-xs">Offset override</p>
                        <Input
                          value={overrides.offset ?? ''}
                          onChange={(e) => updateQueryConfigOverrides(config.key, { offset: e.target.value })}
                          placeholder="Inherit"
                        />
                      </div>
                    </div>

                    <div>
                      <p className="frost-text-muted mb-1 text-xs">Filter override (optional)</p>
                      <Input
                        value={overrides.filter ?? ''}
                        onChange={(e) => updateQueryConfigOverrides(config.key, { filter: e.target.value })}
                        placeholder="Inherit"
                      />
                    </div>

                    <DateRangeFields
                      value={overrides.date_range ?? DATE_RANGE.NONE}
                      onDateRangeChange={(next) => updateQueryConfigOverrides(config.key, { date_range: next })}
                      startKey={overrides.start_date_param ?? DEFAULT_START_DATE_PARAM}
                      onStartKeyChange={(next) => updateQueryConfigOverrides(config.key, { start_date_param: next })}
                      endKey={overrides.end_date_param ?? DEFAULT_END_DATE_PARAM}
                      onEndKeyChange={(next) => updateQueryConfigOverrides(config.key, { end_date_param: next })}
                    />

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <p className="frost-text-muted mb-1 text-xs">Params override (optional JSON)</p>
                        <Textarea
                          value={overrides.paramsJson ?? ''}
                          onChange={(e) => updateQueryConfigOverrides(config.key, { paramsJson: e.target.value })}
                          placeholder={QUERY_PARAMS_PLACEHOLDER}
                          className="min-h-20 font-mono text-xs"
                        />
                      </div>
                      <div>
                        <p className="frost-text-muted mb-1 text-xs">Column styles override (optional JSON)</p>
                        <Textarea
                          value={overrides.columnStylesJson ?? ''}
                          onChange={(e) => updateQueryConfigOverrides(config.key, { columnStylesJson: e.target.value })}
                          placeholder={COLUMN_STYLES_PLACEHOLDER}
                          className="min-h-20 font-mono text-xs"
                        />
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}

          <button
            type="button"
            onClick={addQueryConfig}
            disabled={queryConfigs.length >= availableQueryIds.length}
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
