// Retry settings of a trigger_api_service function node, as the property panel shows them.
// Mirrors tools_module/utils/api_service_fn.py (retry_delays and the defaults there): keep the
// two in step, or the panel shows waits the run won't use.
//
// The retry window is a hard cap on the whole node: the most it may hold the run, attempts and
// waits together. The backend enforces it with a deadline.

export const API_SERVICE_FUNCTION = 'trigger_api_service';
export const REQUEST_TIMEOUT_SECONDS = 60;
export const DEFAULT_MAX_RETRIES = 5;
export const DEFAULT_RETRY_WINDOW_SECONDS = 900;
export const MAX_RETRIES_CAP = 10;

export interface RetrySettings {
  enabled: boolean;
  maxRetries: number;
  windowSeconds: number;
}

const toNumber = (value: unknown): number | undefined => {
  if (value === undefined || value === null || value === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};

// Same reading as the backend: YAML may carry true/'true'/1, and numbers as strings.
export const readRetrySettings = (params: Record<string, unknown> | undefined): RetrySettings => {
  const raw = params?.retry_enabled;
  const enabled =
    typeof raw === 'string' ? ['true', '1', 'yes', 'on'].includes(raw.trim().toLowerCase()) : Boolean(raw);
  const retries = Math.trunc(toNumber(params?.max_retries) ?? DEFAULT_MAX_RETRIES);
  const window = toNumber(params?.retry_window_seconds) ?? DEFAULT_RETRY_WINDOW_SECONDS;
  return {
    enabled,
    maxRetries: Math.min(Math.max(retries, 0), MAX_RETRIES_CAP),
    windowSeconds: Math.max(window, 0),
  };
};

/** Seconds of the window left for waiting once every attempt is allowed its full timeout. */
export const waitBudgetSeconds = (maxRetries: number, windowSeconds: number): number =>
  Math.max(windowSeconds - (Math.max(maxRetries, 0) + 1) * REQUEST_TIMEOUT_SECONDS, 0);

/** The wait before each retry: doubling, and adding up to the wait budget. */
export const retryDelays = (maxRetries: number, windowSeconds: number): number[] => {
  if (maxRetries <= 0) return [];
  const first = waitBudgetSeconds(maxRetries, windowSeconds) / (2 ** maxRetries - 1);
  return Array.from({ length: maxRetries }, (_, i) => first * 2 ** i);
};

/** 29s, 1.9 min, 15 min. */
export const formatDuration = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round((seconds / 60) * 10) / 10;
  return `${minutes} min`;
};
