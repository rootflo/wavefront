import yaml from 'js-yaml';

export const getFunctionNameFromFileName = (file: string): string => file.replace(/\.(ya?ml)$/i, '').trim();

export const validateFunctionYaml = (yamlStr: string): { valid: boolean; error: string } => {
  try {
    const data = yaml.load(yamlStr);
    if (data == null || typeof data !== 'object' || Array.isArray(data)) {
      return { valid: false, error: 'Not a function YAML' };
    }

    const record = data as Record<string, unknown>;
    if ('queries' in record && !('function' in record)) {
      return { valid: false, error: 'Not a function YAML' };
    }

    const requiredTop = ['function', 'input_schema', 'type', 'description'];
    const missing = requiredTop.filter((field) => !(field in record));
    if (missing.length > 0) {
      return { valid: false, error: `Missing top-level field: ${missing.join(', ')}` };
    }

    if (typeof record.type !== 'string' || !record.type.trim()) {
      return { valid: false, error: 'type must be a string' };
    }
    if (typeof record.description !== 'string') {
      return { valid: false, error: 'description must be a string' };
    }

    const fn = record.function;
    if (typeof fn !== 'object' || fn === null || Array.isArray(fn)) {
      return { valid: false, error: 'function must be an object' };
    }
    const code = (fn as Record<string, unknown>).code;
    if (typeof code !== 'string' || !code.trim()) {
      return { valid: false, error: 'function.code is required' };
    }

    const inputSchema = record.input_schema;
    if (typeof inputSchema !== 'object' || inputSchema === null || Array.isArray(inputSchema)) {
      return { valid: false, error: 'input_schema must be an object' };
    }
    const required = (inputSchema as Record<string, unknown>).required;
    if (required != null && !Array.isArray(required)) {
      return { valid: false, error: 'input_schema.required must be a list' };
    }

    return { valid: true, error: '' };
  } catch {
    return { valid: false, error: 'Invalid YAML format' };
  }
};

export const parseUploadedFunction = (
  filename: string,
  content: string,
  existingNames: Set<string>,
  seenNames: Set<string>
): { name: string; description?: string; error: string } => {
  if (!/\.ya?ml$/i.test(filename)) {
    return { name: '', error: 'File must be a YAML file' };
  }
  if (!content.trim()) {
    return { name: '', error: 'File is empty' };
  }

  const name = getFunctionNameFromFileName(filename);
  const validation = validateFunctionYaml(content);
  if (!validation.valid) {
    return { name, error: validation.error };
  }

  if (!name) {
    return { name: '', error: 'Missing function name in filename' };
  }

  const nameKey = name.toLowerCase();
  if (existingNames.has(nameKey)) {
    return { name, error: `A function named "${name}" already exists` };
  }
  if (seenNames.has(nameKey)) {
    return { name, error: `Duplicate name "${name}" in this upload` };
  }
  seenNames.add(nameKey);

  let description: string | undefined;
  try {
    const data = yaml.load(content) as Record<string, unknown>;
    description = typeof data.description === 'string' ? data.description.trim() : undefined;
  } catch {
    description = undefined;
  }

  return { name, description: description || undefined, error: '' };
};
