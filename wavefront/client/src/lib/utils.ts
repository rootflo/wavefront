import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import yaml from 'js-yaml';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Extracts error message from various error object structures.
 * Prioritizes the backend response format:
 * - error.response.data.meta.error (primary backend format: { meta: { status: 'failure', code: -1, error: 'message' } })
 * - error.response.data.error.message (nested error object)
 * - error.response.data.error (string)
 * - error.response.data.message
 * - error.message
 *
 * @param error - The error object (unknown type)
 * @returns The extracted error message string, or undefined if no message found
 */
export function extractErrorMessage(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') {
    return undefined;
  }

  // Check if it's an axios-like error with response
  if ('response' in error) {
    const response = (error as { response?: { data?: unknown } }).response;
    if (response?.data && typeof response.data === 'object' && response.data !== null) {
      const data = response.data as Record<string, unknown>;

      // Primary: Try meta.error (backend format: ResponseModel with meta.error)
      if (data.meta && typeof data.meta === 'object' && data.meta !== null) {
        const meta = data.meta as Record<string, unknown>;
        if (typeof meta.error === 'string' && meta.error) {
          return meta.error;
        }
      }

      // Fallback: Try error.message (nested error object)
      if (data.error && typeof data.error === 'object' && data.error !== null) {
        const errorObj = data.error as Record<string, unknown>;
        if (typeof errorObj.message === 'string') {
          return errorObj.message;
        }
      }

      // Fallback: Try error as string
      if (typeof data.error === 'string' && data.error) {
        return data.error;
      }

      // Fallback: Try data.message
      if (typeof data.message === 'string' && data.message) {
        return data.message;
      }
    }
  }

  // Fallback: Try direct error.message
  if ('message' in error && typeof (error as { message?: unknown }).message === 'string') {
    return (error as { message: string }).message;
  }

  return undefined;
}

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
        const allowed = ['string', 'number', 'boolean', 'date'];

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
