import { downloadTextFile, validateDynamicQueryYaml } from '@app/lib/utils';
import { DynamicQueryItem } from '@app/types/datasource';
import yaml from 'js-yaml';

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
