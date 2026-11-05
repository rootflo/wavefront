/**
 * Whether any of `values` contains `query`, ignoring case and surrounding spaces. A blank query matches
 * everything; missing values are skipped, so optional fields can be passed as they are.
 */
export const matchesSearch = (query: string, ...values: (string | null | undefined)[]): boolean => {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return values.some((value) => value?.toLowerCase().includes(needle));
};
