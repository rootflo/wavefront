const INVALID_FILE_FORMAT = /invalid file format/i;

/**
 * Restores the last accepted conversation after an inference request fails.
 * Invalid file payloads are discarded so a later text-only turn cannot resend
 * the rejected bytes from either chat history or the pending attachment list.
 *
 * @template T
 * @param {T[]} historyBeforeRequest
 * @param {string | undefined} errorMessage
 * @param {string} inputBeforeRequest
 * @returns {{ history: T[]; input: string; clearAttachments: boolean }}
 */
export function recoverFailedInference(historyBeforeRequest, errorMessage, inputBeforeRequest = '') {
  return {
    history: historyBeforeRequest,
    input: inputBeforeRequest,
    clearAttachments: typeof errorMessage === 'string' && INVALID_FILE_FORMAT.test(errorMessage),
  };
}
