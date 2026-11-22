// Helpers for showing rows of any shape, shared by the data browser, operations and query results.

export type SortState = { column: string; direction: 'asc' | 'desc' } | null;

export const formatCellValue = (value: unknown): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

/** Every key that appears in any row, in first-seen order. */
export const recordColumns = (records: Record<string, unknown>[]) => {
  const keys = new Set<string>();
  records.forEach((row) => Object.keys(row).forEach((key) => keys.add(key)));
  return Array.from(keys);
};
