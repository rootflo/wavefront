import { describe, expect, it } from 'vitest';
import { formatDuration, readRetrySettings, retryDelays, waitBudgetSeconds } from './apiServiceRetry';

describe('readRetrySettings', () => {
  it('defaults to off, 5 retries, 15 minutes', () => {
    expect(readRetrySettings(undefined)).toEqual({ enabled: false, maxRetries: 5, windowSeconds: 900 });
  });

  it('reads YAML-style strings like the backend', () => {
    expect(readRetrySettings({ retry_enabled: 'true', max_retries: '3', retry_window_seconds: '600' })).toEqual({
      enabled: true,
      maxRetries: 3,
      windowSeconds: 600,
    });
    expect(readRetrySettings({ retry_enabled: 'no' }).enabled).toBe(false);
  });

  it('caps retries at 10 and floors negatives at 0', () => {
    expect(readRetrySettings({ max_retries: 50 }).maxRetries).toBe(10);
    expect(readRetrySettings({ max_retries: -2, retry_window_seconds: -5 })).toMatchObject({
      maxRetries: 0,
      windowSeconds: 0,
    });
  });
});

describe('retry timing (same numbers as api_service_fn.py)', () => {
  it('fits the waits and every attempt timing out inside the window', () => {
    // 900s window, 6 attempts x 60s = 360s, so 540s is left to wait in
    const delays = retryDelays(5, 900);
    expect(delays.map((d) => Math.round(d * 100) / 100)).toEqual([17.42, 34.84, 69.68, 139.35, 278.71]);
    expect(delays.reduce((a, b) => a + b, 0)).toBeCloseTo(540);
    expect(retryDelays(3, 900).map((d) => Math.round(d * 100) / 100)).toEqual([94.29, 188.57, 377.14]);
    expect(retryDelays(0, 900)).toEqual([]);
  });

  it('has no waits left when the window is too short for the retries', () => {
    expect(waitBudgetSeconds(5, 120)).toBe(0);
    expect(retryDelays(5, 120)).toEqual([0, 0, 0, 0, 0]);
  });

  it('formats durations', () => {
    expect(formatDuration(17.42)).toBe('17s');
    expect(formatDuration(139.35)).toBe('2.3 min');
    expect(formatDuration(900)).toBe('15 min');
  });
});
