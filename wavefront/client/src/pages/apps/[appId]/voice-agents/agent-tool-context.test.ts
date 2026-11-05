import { describe, expect, it } from 'vitest';
import {
  argumentSource,
  contextSummary,
  describeOnCall,
  effectiveMethod,
  isReusedInCall,
  prefetchBlockers,
  readToolContext,
  suggestedSource,
  toolArguments,
  writeToolContext,
} from './agent-tool-context';

const MOBILE = { name: 'mobile_number', required: true };
const PRODUCT = { name: 'product_type', required: false };

describe('toolArguments', () => {
  it('reads names, descriptions and required flags from the schema', () => {
    expect(
      toolArguments({
        parameter_schema: {
          properties: { mobile_number: { type: 'string', description: 'Customer mobile' }, product_type: {} },
          required: ['mobile_number'],
        },
      })
    ).toEqual([
      { name: 'mobile_number', description: 'Customer mobile', required: true },
      { name: 'product_type', description: undefined, required: false },
    ]);
  });

  it('copes with a missing schema', () => {
    expect(toolArguments({ parameter_schema: undefined })).toEqual([]);
  });
});

describe('readToolContext', () => {
  it('reads saved settings and ignores unknown sources', () => {
    expect(
      readToolContext({
        timeout: 3,
        context: { bind: { mobile_number: 'caller.phone', x: 'caller.email' }, read_only: true, prefetch: true },
      })
    ).toEqual({ bind: { mobile_number: 'caller.phone' }, readOnly: true, prefetch: true });
  });

  it('defaults to nothing set', () => {
    expect(readToolContext(undefined)).toEqual({ bind: {}, readOnly: false, prefetch: false });
  });
});

describe('writeToolContext', () => {
  it('keeps other overrides and other context keys', () => {
    expect(
      writeToolContext(
        { timeout: 3, context: { prompt_fields: ['name'], prefetch: true } },
        { bind: { mobile_number: 'caller.phone' }, readOnly: true, prefetch: false }
      )
    ).toEqual({
      timeout: 3,
      context: { prompt_fields: ['name'], bind: { mobile_number: 'caller.phone' }, read_only: true },
    });
  });

  it('removes the context block when nothing is set', () => {
    expect(
      writeToolContext(
        { timeout: 3, context: { bind: { a: 'call.id' } } },
        { bind: {}, readOnly: false, prefetch: false }
      )
    ).toEqual({ timeout: 3 });
  });
});

describe('effectiveMethod', () => {
  it('prefers the association override', () => {
    const tool = { config: { method: 'GET' as const, url: 'https://x' } };
    expect(effectiveMethod(tool, undefined)).toBe('GET');
    expect(effectiveMethod(tool, { method: 'post' })).toBe('POST');
  });
});

describe('prefetchBlockers', () => {
  it('allows a GET tool whose every detail is server-filled', () => {
    expect(prefetchBlockers([MOBILE], 'GET', { bind: { mobile_number: 'caller.phone' }, readOnly: false })).toEqual([]);
  });

  it('names the details still left to the AI', () => {
    const [blocker] = prefetchBlockers([MOBILE, PRODUCT], 'GET', {
      bind: { mobile_number: 'caller.phone' },
      readOnly: false,
    });
    expect(blocker).toContain('Still set to the AI: product_type.');
  });

  it('blocks a write request unless it is marked read-only', () => {
    const settings = { bind: { mobile_number: 'caller.phone' as const }, readOnly: false };
    expect(prefetchBlockers([MOBILE], 'POST', settings)[0]).toContain('POST request');
    expect(prefetchBlockers([MOBILE], 'POST', { ...settings, readOnly: true })).toEqual([]);
  });
});

describe('isReusedInCall', () => {
  it('matches the server rule', () => {
    expect(isReusedInCall('POST', { bind: {}, readOnly: true, prefetch: false })).toBe(true);
    expect(isReusedInCall('GET', { bind: {}, readOnly: false, prefetch: true })).toBe(true);
    expect(isReusedInCall('GET', { bind: {}, readOnly: false, prefetch: false })).toBe(false);
    expect(isReusedInCall('POST', { bind: {}, readOnly: false, prefetch: true })).toBe(false);
  });
});

describe('argumentSource', () => {
  it('is the AI unless the server fills it', () => {
    const settings = { bind: { mobile_number: 'caller.phone' as const } };
    expect(argumentSource(settings, 'mobile_number')).toBe('caller.phone');
    expect(argumentSource(settings, 'product_type')).toBe('ai');
  });
});

describe('suggestedSource', () => {
  it.each([
    ['mobile_number', 'caller.phone'],
    ['customerPhone', 'caller.phone'],
    ['contact_no', 'caller.phone'],
    ['call_sid', 'call.id'],
    ['product_type', undefined],
  ])('%s -> %s', (name, expected) => {
    expect(suggestedSource({ name, required: false })).toBe(expected);
  });
});

describe('describeOnCall', () => {
  it('says nothing changes when nothing is set', () => {
    expect(describeOnCall('GET', { bind: {}, readOnly: false, prefetch: false }, false)).toEqual([
      expect.stringContaining('Works as it does today'),
    ]);
  });

  it('describes filling, prefetch and reuse', () => {
    const settings = { bind: { mobile_number: 'caller.phone' as const }, readOnly: false, prefetch: true };
    const lines = describeOnCall('GET', settings, true);
    expect(lines).toEqual([
      expect.stringContaining(`caller's phone number as "mobile_number"`),
      expect.stringContaining('runs as the call starts'),
      expect.stringContaining('saved answer is reused'),
    ]);
  });

  it('leaves out a prefetch that is blocked', () => {
    const lines = describeOnCall('POST', { bind: {}, readOnly: false, prefetch: true }, false);
    expect(lines).toEqual([expect.stringContaining('Works as it does today')]);
  });
});

describe('contextSummary', () => {
  const tool = {
    config: { method: 'GET' as const, url: 'https://x' },
    parameter_schema: { properties: { mobile_number: {} } },
  };

  it('is empty when nothing is set', () => {
    expect(contextSummary(tool, { timeout: 3 })).toBeUndefined();
  });

  it('names the strongest setting', () => {
    const bind = { mobile_number: 'caller.phone' };
    expect(contextSummary(tool, { context: { bind, prefetch: true } })).toBe('Looked up at call start');
    expect(contextSummary(tool, { context: { bind } })).toBe('Details auto-filled');
    expect(contextSummary(tool, { context: { read_only: true } })).toBe('Reused in call');
  });
});
