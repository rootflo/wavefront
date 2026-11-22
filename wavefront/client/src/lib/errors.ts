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
