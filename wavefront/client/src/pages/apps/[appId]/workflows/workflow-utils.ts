import yaml from 'js-yaml';

export const getNameFromFileName = (file: string): string => file.replace(/\.(ya?ml)$/i, '').trim();

export const validateWorkflowYaml = (yamlStr: string): { valid: boolean; error: string } => {
  try {
    const data = yaml.load(yamlStr);
    if (data == null || typeof data !== 'object' || Array.isArray(data)) {
      return { valid: false, error: 'Not a workflow YAML' };
    }

    const record = data as Record<string, unknown>;
    if ('function' in record && 'input_schema' in record) {
      return { valid: false, error: 'Not a workflow YAML' };
    }
    if ('queries' in record && !('arium' in record)) {
      return { valid: false, error: 'Not a workflow YAML' };
    }

    const arium = record.arium;
    if (typeof arium !== 'object' || arium === null || Array.isArray(arium)) {
      return { valid: false, error: 'Missing top-level field: arium' };
    }

    const workflow = (arium as Record<string, unknown>).workflow;
    if (typeof workflow !== 'object' || workflow === null || Array.isArray(workflow)) {
      return { valid: false, error: 'Missing field: arium.workflow' };
    }

    if (!('start' in (workflow as Record<string, unknown>))) {
      return { valid: false, error: 'Missing field: arium.workflow.start' };
    }

    return { valid: true, error: '' };
  } catch {
    return { valid: false, error: 'Invalid YAML format' };
  }
};

export const parseUploadedWorkflow = (
  filename: string,
  content: string,
  existingNames: Set<string>,
  seenNames: Set<string>
): { name: string; error: string } => {
  if (!/\.ya?ml$/i.test(filename)) {
    return { name: '', error: 'File must be a YAML file' };
  }
  if (!content.trim()) {
    return { name: '', error: 'File is empty' };
  }

  const name = getNameFromFileName(filename);
  const validation = validateWorkflowYaml(content);
  if (!validation.valid) {
    return { name, error: validation.error };
  }

  if (!name) {
    return { name: '', error: 'Missing workflow name in filename' };
  }

  const nameKey = name.toLowerCase();
  if (existingNames.has(nameKey)) {
    return { name, error: `A workflow named "${name}" already exists` };
  }
  if (seenNames.has(nameKey)) {
    return { name, error: `Duplicate name "${name}" in this upload` };
  }
  seenNames.add(nameKey);

  return { name, error: '' };
};
