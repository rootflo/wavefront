import { downloadTextFile } from '@app/utils/download';
import { DynamicQueryItem } from '@app/types/datasource';
import yaml from 'js-yaml';

export const validateDynamicQueryYaml = (yaml_str: string) => {
  try {
    const data = yaml.load(yaml_str) as Record<string, unknown>;
    // top require keys
    const requiredTop = ['id', 'name', 'queries'];

    for (const field of requiredTop) {
      if (!(field in data)) {
        return { valid: false, error: `Missing top-level field: ${field}` };
      }
    }
    // ✅ queries must be a list
    if (!Array.isArray(data.queries)) {
      return { valid: false, error: 'queries must be a list' };
    }
    // each query must constain id,description,query
    for (let i = 0; i < data.queries.length; i++) {
      const q = data.queries[i];
      for (const field of ['id', 'description', 'query']) {
        if (!(field in q)) {
          return {
            valid: false,
            error: `Missing field ${field} in query ${i + 1}`,
          };
        }
      }
      if ('parameters' in q) {
        if (typeof q.parameters !== 'object') {
          return {
            valid: false,
            error: 'parameters must be an object or array',
          };
        }
        const allowed = ['string', 'number', 'boolean', 'date', 'timestamp'];

        // Handle array format: [{ name: 'param1', type: 'date' }, ...]
        if (Array.isArray(q.parameters)) {
          for (let j = 0; j < q.parameters.length; j++) {
            const param = q.parameters[j];
            if (typeof param !== 'object' || param === null) {
              return {
                valid: false,
                error: `Parameter ${j + 1} in query ${i + 1} must be an object`,
              };
            }
            if (!('name' in param)) {
              return {
                valid: false,
                error: `Missing 'name' field in parameter ${j + 1} of query ${i + 1}`,
              };
            }
            if (!('type' in param)) {
              return {
                valid: false,
                error: `Missing 'type' field in parameter ${j + 1} of query ${i + 1}`,
              };
            }
            if (typeof param.name !== 'string') {
              return {
                valid: false,
                error: `Parameter name must be a string in parameter ${j + 1} of query ${i + 1}`,
              };
            }
            if (!allowed.includes(param.type)) {
              return {
                valid: false,
                error: `Invalid parameter type '${param.type}' in parameter '${
                  param.name
                }' of query ${i + 1}. Allowed types: ${allowed.join(', ')}`,
              };
            }
          }
        }
      }
    }
    return { valid: true, error: '' };
  } catch {
    return { valid: false, error: 'Invalid YAML format' };
  }
};

export { downloadTextFile };

export const buildDynamicQueryYaml = (
  selectedQuery: string | null,
  queryName: string,
  queryItems: DynamicQueryItem[]
): string => {
  if (!selectedQuery || queryItems.length === 0) return '';

  return yaml.dump(
    {
      id: selectedQuery.split('.')[0],
      name: queryName,
      queries: queryItems.map((query) => ({
        id: query.id,
        query: query.query,
        description: query.description ?? '',
        ...(query.parameters && query.parameters.length > 0
          ? {
              parameters: query.parameters.map((param) => ({
                name: param.name,
                type: param.type,
              })),
            }
          : {}),
      })),
    },
    { lineWidth: -1, noRefs: true }
  );
};

export const getDynamicQueryYamlFilename = (file: string): string => {
  return /\.ya?ml$/i.test(file) ? file : `${file}.yaml`;
};

export const getDynamicQueryIdFromFileName = (file: string): string => file.replace(/\.ya?ml$/i, '').trim();

export const parseUploadedDynamicQuery = (
  filename: string,
  content: string,
  existingIds: Set<string>,
  seenIds: Set<string>
): { id: string; error: string } => {
  if (!/\.ya?ml$/i.test(filename)) {
    return { id: '', error: 'File must be a YAML file' };
  }

  const validation = validateDynamicQueryYaml(content);
  if (!validation.valid) {
    return { id: '', error: validation.error };
  }

  let id = '';
  try {
    const data = yaml.load(content) as Record<string, unknown>;
    id = typeof data?.id === 'string' ? data.id.trim() : String(data?.id ?? '').trim();
  } catch {
    return { id: '', error: 'Invalid YAML format' };
  }

  if (!id) {
    return { id: '', error: 'Missing top-level field: id' };
  }
  if (existingIds.has(id)) {
    return { id, error: `A dynamic query with id "${id}" already exists` };
  }
  if (seenIds.has(id)) {
    return { id, error: `Duplicate id "${id}" in this upload` };
  }

  seenIds.add(id);
  return { id, error: '' };
};
