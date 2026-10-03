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

/**
 * Runs an inference request and applies the page recovery actions on failure.
 *
 * @template T, R
 * @param {() => Promise<R>} request
 * @param {{ historyBeforeRequest: T[]; inputBeforeRequest: string; getErrorMessage: (error: unknown) => string | undefined; setChatHistory: (history: T[]) => void; setInferenceInput: (input: string) => void; clearUploadedImages: () => void; clearUploadedDocuments: () => void; notifyError: (message: string) => void }} recovery
 * @returns {Promise<{ success: true; value: R } | { success: false; error: unknown; errorMessage?: string }>}
 */
export async function runInferenceWithRecovery(request, recovery) {
  try {
    return { success: true, value: await request() };
  } catch (error) {
    const errorMessage = recovery.getErrorMessage(error);
    const result = recoverFailedInference(recovery.historyBeforeRequest, errorMessage, recovery.inputBeforeRequest);
    recovery.setChatHistory(result.history);
    recovery.setInferenceInput(result.input);
    if (result.clearAttachments) {
      recovery.clearUploadedImages();
      recovery.clearUploadedDocuments();
    }
    if (errorMessage) recovery.notifyError(errorMessage);
    return { success: false, error, errorMessage };
  }
}
