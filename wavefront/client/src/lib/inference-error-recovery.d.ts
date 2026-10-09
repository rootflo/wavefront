export interface FailedInferenceRecovery<T> {
  history: T[];
  input: string;
  clearAttachments: boolean;
}

export function recoverFailedInference<T>(
  historyBeforeRequest: T[],
  errorMessage?: string,
  inputBeforeRequest?: string
): FailedInferenceRecovery<T>;

export function runInferenceWithRecovery<T, R>(
  request: () => Promise<R>,
  recovery: {
    historyBeforeRequest: T[];
    inputBeforeRequest: string;
    getErrorMessage: (error: unknown) => string | undefined;
    setChatHistory: (history: T[]) => void;
    setInferenceInput: (input: string) => void;
    clearUploadedImages: () => void;
    clearUploadedDocuments: () => void;
    notifyError: (message: string) => void;
  }
): Promise<{ success: true; value: R } | { success: false; error: unknown; errorMessage?: string }>;
