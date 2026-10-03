const INVALID_FILE_FORMAT = /invalid file format/i;

/**
 * Restores the last accepted conversation after an inference request fails.
 * Invalid file payloads are discarded so a later text-only turn cannot resend
 * the rejected bytes from either chat history or the pending attachment list.
 *
 * @template T
 * @param {T[]} historyBeforeRequest
 * @param {string | undefined} errorMessage
 * @returns {{ history: T[]; clearAttachments: boolean }}
 */
export function recoverFailedInference(historyBeforeRequest, errorMessage) {
  return {
    history: historyBeforeRequest,
    clearAttachments: typeof errorMessage === 'string' && INVALID_FILE_FORMAT.test(errorMessage),
  };
}
