import { FormInputField, FormSelectField } from '@app/components/FormFields';
import { Control } from 'react-hook-form';
import { DATE_RANGE_OPTIONS, FIELD_STYLE, ScheduledJobFormValues } from './scheduled-job-form';

interface DateRangeFieldsProps {
  control: Control<ScheduledJobFormValues>;
  /** Where the settings live: the job defaults, or one query's overrides. */
  prefix: 'defaults' | `queries.${number}.overrides`;
}

/** A query's optional dynamic date range, and the param keys its start and end dates are sent as. */
const DateRangeFields = ({ control, prefix }: DateRangeFieldsProps) => (
  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
    <FormSelectField
      {...FIELD_STYLE}
      control={control}
      name={`${prefix}.dateRange`}
      label="Dynamic date range (optional)"
      placeholder="Select range"
      options={DATE_RANGE_OPTIONS}
    />
    <FormInputField {...FIELD_STYLE} control={control} name={`${prefix}.startDateParam`} label="Start date param key" />
    <FormInputField {...FIELD_STYLE} control={control} name={`${prefix}.endDateParam`} label="End date param key" />
  </div>
);

export default DateRangeFields;
