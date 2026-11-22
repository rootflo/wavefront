import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { DateRangeOption } from '@app/types/scheduled-job';
import { DATE_RANGE_OPTIONS, isDateRangeOption } from './scheduled-job-form';

interface DateRangeFieldsProps {
  value: DateRangeOption;
  onDateRangeChange: (next: DateRangeOption) => void;
  startKey: string;
  onStartKeyChange: (next: string) => void;
  endKey: string;
  onEndKeyChange: (next: string) => void;
}

/** A query's optional dynamic date range, and the param keys its start and end dates are sent as. */
const DateRangeFields = ({
  value,
  onDateRangeChange,
  startKey,
  onStartKeyChange,
  endKey,
  onEndKeyChange,
}: DateRangeFieldsProps) => (
  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
    <div>
      <p className="frost-text-muted mb-1 text-xs">Dynamic date range (optional)</p>
      <Select
        value={value}
        onValueChange={(next) => {
          if (isDateRangeOption(next)) onDateRangeChange(next);
        }}
      >
        <SelectTrigger>
          <SelectValue placeholder="Select range" />
        </SelectTrigger>
        <SelectContent>
          {DATE_RANGE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
    <div>
      <p className="frost-text-muted mb-1 text-xs">Start date param key</p>
      <Input value={startKey} onChange={(e) => onStartKeyChange(e.target.value)} />
    </div>
    <div>
      <p className="frost-text-muted mb-1 text-xs">End date param key</p>
      <Input value={endKey} onChange={(e) => onEndKeyChange(e.target.value)} />
    </div>
  </div>
);

export default DateRangeFields;
