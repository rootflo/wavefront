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

      // Fallback: FastAPI validation errors (422) bypass the meta/data
      // envelope entirely and arrive as { detail: [{ loc, msg }] }. Without
      // this branch they surface as "Request failed with status code 422".
      if (Array.isArray(data.detail)) {
        const messages = data.detail
          .map((item) => {
            if (!item || typeof item !== 'object') return undefined;
            const entry = item as Record<string, unknown>;
            if (typeof entry.msg !== 'string') return undefined;
            // loc is ['body', '<field>', ...]; the field name is the useful part.
            const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : '';
            return field ? `${field}: ${entry.msg}` : entry.msg;
          })
          .filter((message): message is string => !!message);

        if (messages.length) {
          return messages.join('; ');
        }
      }

      if (typeof data.detail === 'string' && data.detail) {
        return data.detail;
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

export const downloadBlobFile = (filename: string, blob: Blob) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export const downloadTextFile = (filename: string, content: string, mimeType = 'text/yaml;charset=utf-8') => {
  downloadBlobFile(filename, new Blob([content], { type: mimeType }));
};

const CRC32_TABLE = Uint32Array.from({ length: 256 }, (_, index) => {
  let crc = index;
  for (let bit = 0; bit < 8; bit += 1) {
    crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  }
  return crc >>> 0;
});

const crc32 = (data: Uint8Array) => {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = CRC32_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
};

const concatBytes = (...parts: Uint8Array[]) => {
  const output = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
};

const u16 = (value: number) => {
  const bytes = new Uint8Array(2);
  new DataView(bytes.buffer).setUint16(0, value, true);
  return bytes;
};

const u32 = (value: number) => {
  const bytes = new Uint8Array(4);
  new DataView(bytes.buffer).setUint32(0, value, true);
  return bytes;
};

export const createZipBlob = (files: { filename: string; content: string }[]): Blob => {
  const encoder = new TextEncoder();
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const name = encoder.encode(file.filename);
    const data = encoder.encode(file.content);
    const checksum = crc32(data);
    const local = concatBytes(
      u32(0x04034b50),
      u16(20),
      u16(0x0800),
      u16(0),
      u16(0),
      u16(0),
      u32(checksum),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      name,
      data
    );
    locals.push(local);
    centrals.push(
      concatBytes(
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0x0800),
        u16(0),
        u16(0),
        u16(0),
        u32(checksum),
        u32(data.length),
        u32(data.length),
        u16(name.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        name
      )
    );
    offset += local.length;
  }

  const centralDir = concatBytes(...centrals);
  const archive = concatBytes(
    ...locals,
    centralDir,
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDir.length),
    u32(offset),
    u16(0)
  );

  return new Blob([archive], { type: 'application/zip' });
};

export const getYamlFilename = (name: string): string => {
  const base = (name.trim() || 'file').replace(/[<>:"/\\|?*]/g, '-');
  return /\.ya?ml$/i.test(base) ? base : `${base}.yaml`;
};

export const copyToClipboard = async (text: string): Promise<boolean> => {
  if (!text) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to execCommand when Clipboard API is unavailable.
  }

  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
};
