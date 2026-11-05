/**
 * Caller context typed into the Make call dialog (for manual tests): what a CRM
 * would send as `context` when it starts an outbound call. The rules mirror
 * floware's `InitiateCallPayload.context` validator.
 */

export interface ContextRow {
  key: string;
  value: string;
}

export const MAX_CONTEXT_BYTES = 2048;
const CONTEXT_KEY = /^[a-z0-9_]{1,40}$/;

/**
 * The `context` to send, or the reason it can't be sent. Rows with an empty
 * key and value are ignored; an empty result is `undefined` (send nothing).
 */
export const contextFromRows = (rows: ContextRow[]): { context?: Record<string, string>; error?: string } => {
  const context: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    const value = row.value.trim();
    if (!key && !value) continue;
    if (!CONTEXT_KEY.test(key)) {
      return { error: `"${key || '(empty)'}": keys use lowercase letters, digits and _ (up to 40)` };
    }
    if (key in context) return { error: `"${key}" is used twice` };
    context[key] = value;
  }
  if (Object.keys(context).length === 0) return {};
  if (new TextEncoder().encode(JSON.stringify(context)).length > MAX_CONTEXT_BYTES) {
    return { error: `Caller context is over ${MAX_CONTEXT_BYTES} bytes` };
  }
  return { context };
};
