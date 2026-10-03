export interface FailedInferenceRecovery<T> {
  history: T[];
  clearAttachments: boolean;
}

export function recoverFailedInference<T>(historyBeforeRequest: T[], errorMessage?: string): FailedInferenceRecovery<T>;
