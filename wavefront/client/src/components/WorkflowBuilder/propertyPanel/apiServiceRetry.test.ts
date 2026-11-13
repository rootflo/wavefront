import { describe, expect, it } from 'vitest';
import { formatDuration, maxHoldSeconds, readRetrySettings, retryDelays } from './apiServiceRetry';

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
  it('doubles the waits and fills the window', () => {
    const delays = retryDelays(5, 900);
    expect(delays.map((d) => Math.round(d * 100) / 100)).toEqual([29.03, 58.06, 116.13, 232.26, 464.52]);
    expect(delays.reduce((a, b) => a + b, 0)).toBeCloseTo(900);
    expect(retryDelays(0, 900)).toEqual([]);
  });

  it('holds for the window plus one timeout per attempt', () => {
    expect(maxHoldSeconds(5, 900)).toBe(900 + 6 * 60);
    expect(maxHoldSeconds(3, 900)).toBe(900 + 4 * 60);
  });

  it('formats durations', () => {
    expect(formatDuration(29.03)).toBe('29s');
    expect(formatDuration(116.13)).toBe('1.9 min');
    expect(formatDuration(1260)).toBe('21 min');
  });
});
