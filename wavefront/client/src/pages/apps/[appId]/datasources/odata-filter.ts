// Builds the OData filter strings the datasource API reads, e.g. "status eq 'active' $and amount gte 100".

/**
 * The operators the backend's parser compiles (see plugins/datasource/odata_parser.py). `label` is short so a
 * condition fits on one line in a narrow panel; `title` says it in words.
 */
export const FILTER_OPERATORS = [
  { value: 'eq', label: '=', title: 'equals' },
  { value: 'gt', label: '>', title: 'greater than' },
  { value: 'gte', label: '≥', title: 'at least' },
  { value: 'lt', label: '<', title: 'less than' },
  { value: 'lte', label: '≤', title: 'at most' },
  { value: 'contains', label: 'contains', title: 'contains' },
  { value: 'in', label: 'is one of', title: 'is one of' },
] as const;

export type FilterOperator = (typeof FILTER_OPERATORS)[number]['value'];
export type FilterJoin = '$and' | '$or';

export interface FilterCondition {
  column: string;
  operator: FilterOperator;
  value: string;
}

const NUMBER_OR_BOOLEAN = /^(-?\d+(\.\d+)?|true|false)$/i;

/** A literal as the parser expects it: numbers and booleans bare, everything else in single quotes. */
export const formatFilterValue = (value: unknown): string => {
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  const text = String(value ?? '').trim();
  if (NUMBER_OR_BOOLEAN.test(text)) return text;
  return `'${text.replace(/'/g, "''")}'`;
};

const formatCondition = ({ column, operator, value }: FilterCondition) => {
  if (operator === 'in') {
    const items = value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
      .map(formatFilterValue);
    return `${column.trim()} in [${items.join(', ')}]`;
  }
  return `${column.trim()} ${operator} ${formatFilterValue(value)}`;
};

/** Joins the complete conditions; half-filled ones are skipped rather than sent. */
export const buildFilter = (conditions: FilterCondition[], join: FilterJoin = '$and'): string =>
  conditions
    .filter((condition) => condition.column.trim() && condition.value.trim())
    .map(formatCondition)
    .join(` ${join} `);

/** The filter that names exactly one row by its key column. */
export const rowKeyFilter = (column: string, value: unknown) => `${column} eq ${formatFilterValue(value)}`;
