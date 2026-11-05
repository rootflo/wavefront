import { DynamicQueryItem } from '@app/types/datasource';

// What a dynamic query asks for when it runs. The backend binds `:name` placeholders from each query's declared
// `parameters`, replaces `{{filters}}` with an OData filter, and pages every query with limit and offset.

export type ParameterType = 'string' | 'number' | 'boolean' | 'date';

export interface QueryParameter {
  name: string;
  type: ParameterType;
  /** Ids of the queries in the YAML that declare it. */
  usedBy: string[];
}

const PARAMETER_TYPES: ParameterType[] = ['string', 'number', 'boolean', 'date'];

// `:name`, but not the `::type` of a cast. Same pattern the backend uses to bind parameters.
const PLACEHOLDER = /(?<!:):([A-Za-z_][A-Za-z0-9_]*)/g;
// Quoted text is data, not SQL; a time like '10:30' must not read as a placeholder.
const QUOTED = /'(?:[^']|'')*'/g;

/** Every declared parameter once, with the queries that use it, in the order they first appear. */
export const collectParameters = (items: DynamicQueryItem[]): QueryParameter[] => {
  const byName = new Map<string, QueryParameter>();
  items.forEach((item) =>
    (item.parameters ?? []).forEach(({ name, type }) => {
      const existing = byName.get(name);
      if (existing) {
        existing.usedBy.push(item.id);
      } else {
        const known = PARAMETER_TYPES.includes(type as ParameterType) ? (type as ParameterType) : 'string';
        byName.set(name, { name, type: known, usedBy: [item.id] });
      }
    })
  );
  return Array.from(byName.values());
};

/** `:name` placeholders a query uses without declaring; the backend would fail to bind them. */
export const undeclaredPlaceholders = (items: DynamicQueryItem[]): { queryId: string; names: string[] }[] =>
  items
    .map((item) => {
      const declared = new Set((item.parameters ?? []).map((parameter) => parameter.name));
      const used = new Set(
        Array.from((item.query ?? '').replace(QUOTED, '').matchAll(PLACEHOLDER), (match) => match[1])
      );
      return { queryId: item.id, names: Array.from(used).filter((name) => !declared.has(name)) };
    })
    .filter((entry) => entry.names.length > 0);

/** Whether any query takes a run-time OData filter through `{{filters}}`. */
export const usesFilters = (items: DynamicQueryItem[]) =>
  items.some((item) => (item.query ?? '').includes('{{filters}}'));
