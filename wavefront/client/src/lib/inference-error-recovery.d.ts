export interface FailedInferenceRecovery<T> {
  history: T[];
  clearAttachments: boolean;
}

export function recoverFailedInference<T>(
  historyBeforeRequest: T[],
  errorMessage?: string,
  inputBeforeRequest?: string
): FailedInferenceRecovery<T> & { input: string };
