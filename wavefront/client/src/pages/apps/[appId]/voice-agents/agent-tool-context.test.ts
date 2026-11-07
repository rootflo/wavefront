import { describe, expect, it } from 'vitest';
import {
  argumentSource,
  contextSummary,
  describeOnCall,
  effectiveMethod,
  fieldLabel,
  parsePromptFields,
  isReusedInCall,
  prefetchBlockers,
  readToolContext,
  sourceOption,
  sourceOptions,
  suggestedSource,
  toolArguments,
  usableBind,
  writeToolContext,
} from './agent-tool-context';

const MOBILE = { name: 'mobile_number', required: true, bindable: true, parents: [] };
const SERVICE = { name: 'service', required: true, bindable: true, parents: [] };

// Made-up scenario: a water utility helpline whose tools take one `request` object.
// find_account needs only the caller's phone; get_bill also needs the service asked about.
const LANGUAGE = { enum: ['en', 'hi'], type: 'string' };
const FIND_ACCOUNT = {
  type: 'object',
  required: ['request'],
  properties: {
    request: {
      type: 'object',
      required: ['phone'],
      properties: { phone: { type: 'string' } },
    },
  },
};
const GET_BILL = {
  type: 'object',
  required: ['request'],
  properties: {
    request: {
      type: 'object',
      required: ['service'],
      properties: {
        language: LANGUAGE,
        period: { type: 'string' },
        service: { enum: ['water', 'sewer'], type: 'string' },
        phone: { type: 'string' },
      },
    },
  },
};
const PHONE_BIND = { 'request.phone': 'caller.phone' as const };

describe('toolArguments', () => {
  it('reads names, descriptions and required flags from the schema', () => {
    expect(
      toolArguments({
        parameter_schema: {
          properties: { mobile_number: { type: 'string', description: 'Caller mobile' }, service: {} },
          required: ['mobile_number'],
        },
      })
    ).toEqual([
      { name: 'mobile_number', description: 'Caller mobile', required: true, bindable: true, parents: [] },
      { name: 'service', description: undefined, required: false, bindable: false, parents: [] },
    ]);
  });

  it('opens an object argument up into its fields', () => {
    const parents = [{ name: 'request', required: true }];
    expect(toolArguments({ parameter_schema: GET_BILL })).toEqual([
      { name: 'request.language', description: undefined, required: false, bindable: true, parents },
      { name: 'request.period', description: undefined, required: false, bindable: true, parents },
      { name: 'request.service', description: undefined, required: true, bindable: true, parents },
      { name: 'request.phone', description: undefined, required: false, bindable: true, parents },
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
    ).toEqual({ bind: { mobile_number: 'caller.phone' }, readOnly: true, prefetch: true, promptFields: [] });
  });

  it('keeps outbound.<key> binds set through the API', () => {
    expect(readToolContext({ context: { bind: { loan_id: 'outbound.loan_id', x: 'outbound.' } } }).bind).toEqual({
      loan_id: 'outbound.loan_id',
    });
  });

  it('defaults to nothing set', () => {
    expect(readToolContext(undefined)).toEqual({ bind: {}, readOnly: false, prefetch: false, promptFields: [] });
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

describe('outbound binds round trip', () => {
  const saved = { context: { bind: { loan_id: 'outbound.loan_id', mobile_number: 'caller.phone' } } };

  it('saving the dialog keeps them', () => {
    expect(writeToolContext(saved, readToolContext(saved))).toEqual(saved);
  });

  it('are shown as CRM context and stay selectable', () => {
    expect(sourceOption('outbound.loan_id').label).toBe('CRM context: loan_id');
    expect(sourceOptions('outbound.loan_id').map((s) => s.value)).toContain('outbound.loan_id');
    expect(sourceOptions('caller.phone').some((s) => s.value.startsWith('outbound.'))).toBe(false);
  });

  it('are described in plain words', () => {
    const settings = { bind: { loan_id: 'outbound.loan_id' as const }, readOnly: false, prefetch: false };
    expect(describeOnCall('GET', settings, false)[0]).toContain(`the CRM's "loan_id" value`);
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
    const [blocker] = prefetchBlockers([MOBILE, SERVICE], 'GET', {
      bind: { mobile_number: 'caller.phone' },
      readOnly: false,
    });
    expect(blocker).toContain('Still set to the AI: service.');
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
    expect(argumentSource(settings, 'service')).toBe('ai');
  });
});

describe('suggestedSource', () => {
  it.each([
    ['mobile_number', 'caller.phone'],
    ['customerPhone', 'caller.phone'],
    ['contact_no', 'caller.phone'],
    ['call_sid', 'call.id'],
    ['service', undefined],
    // Whole name parts only, camelCase included
    ['phoneNumber', 'caller.phone'],
    ['telephone', 'caller.phone'],
    ['contactNumber', 'caller.phone'],
    ['CallSid', 'call.id'],
    ['callid', 'call.id'],
    ['automobile_make', undefined],
    ['cancellation_reason', undefined],
    ['recall_id', undefined],
    ['microphone_model', undefined],
  ])('%s -> %s', (name, expected) => {
    expect(suggestedSource({ name, required: false, bindable: true, parents: [] })).toBe(expected);
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
    parameter_schema: { properties: { mobile_number: { type: 'string' } } },
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

describe('nested fields (water helpline scenario)', () => {
  const findAccount = toolArguments({ parameter_schema: FIND_ACCOUNT });
  const getBill = toolArguments({ parameter_schema: GET_BILL });

  it('shows paths readably', () => {
    expect(fieldLabel('request.phone')).toBe('request › phone');
  });

  it('lets find_account run early once its phone is filled', () => {
    expect(prefetchBlockers(findAccount, 'POST', { bind: PHONE_BIND, readOnly: true })).toEqual([]);
  });

  it('blocks on a required field only the AI can fill', () => {
    const requiredLanguage = {
      ...FIND_ACCOUNT,
      properties: {
        request: {
          type: 'object',
          required: ['phone', 'language'],
          properties: { phone: { type: 'string' }, language: LANGUAGE },
        },
      },
    };
    const args = toolArguments({ parameter_schema: requiredLanguage });
    const [blocker] = prefetchBlockers(args, 'POST', { bind: PHONE_BIND, readOnly: true });
    expect(blocker).toContain('Still set to the AI: request › language.');
  });

  it('names the nested required field that blocks get_bill', () => {
    const [blocker] = prefetchBlockers(getBill, 'POST', { bind: PHONE_BIND, readOnly: true });
    expect(blocker).toContain('Still set to the AI: request › service.');
  });

  it('counts nested required fields even when nothing is bound', () => {
    const [blocker] = prefetchBlockers(findAccount, 'GET', { bind: {}, readOnly: false });
    expect(blocker).toContain('request › phone');
  });

  it('suggests the caller phone for the nested phone field', () => {
    const phone = findAccount.find((a) => a.name === 'request.phone')!;
    expect(suggestedSource(phone)).toBe('caller.phone');
    expect(suggestedSource(getBill.find((a) => a.name === 'request.language')!)).toBeUndefined();
  });

  it('ignores the old bind on the whole object and keeps the field bind', () => {
    expect(usableBind(getBill, { request: 'caller.phone', ...PHONE_BIND })).toEqual({
      bind: PHONE_BIND,
      ignored: ['request'],
    });
  });

  it('does not offer call values for non-text fields', () => {
    const [count] = toolArguments({
      parameter_schema: { properties: { count: { type: 'integer' } }, required: ['count'] },
    });
    expect(count.bindable).toBe(false);
    expect(suggestedSource({ ...count, name: 'phone_count' })).toBeUndefined();
  });

  it('summarises the old object bind as not set', () => {
    const tool = { config: { method: 'POST' as const, url: 'https://x' }, parameter_schema: GET_BILL };
    expect(contextSummary(tool, { context: { bind: { request: 'caller.phone' } } })).toBeUndefined();
  });
});

describe('prompt fields', () => {
  it('reads saved paths and skips non-text entries', () => {
    const overrides = { context: { prompt_fields: ['customer_name', 3, ' ', 'account.amount_due'] } };
    expect(readToolContext(overrides).promptFields).toEqual(['customer_name', 'account.amount_due']);
  });

  it('parses one path per line', () => {
    expect(parsePromptFields(' customer_name \n\naccount.amount_due\ncustomer_name')).toEqual([
      'customer_name',
      'account.amount_due',
    ]);
  });

  it('saves them, removes them when emptied, and keeps them when not managed', () => {
    const base = { bind: {}, readOnly: true, prefetch: true };
    const saved = { context: { prompt_fields: ['customer_name'], prefetch: true, read_only: true } };
    expect(writeToolContext(undefined, { ...base, promptFields: ['customer_name'] })).toEqual(saved);
    expect(writeToolContext(saved, { ...base, promptFields: [] })).toEqual({
      context: { prefetch: true, read_only: true },
    });
    expect(writeToolContext(saved, base)).toEqual(saved);
  });

  it('says what the AI gets up front, only when the lookup runs early', () => {
    const settings = { bind: {}, readOnly: true, prefetch: true, promptFields: ['account.amount_due'] };
    expect(describeOnCall('GET', settings, true)).toContainEqual(
      expect.stringContaining('given account › amount_due up front')
    );
    expect(describeOnCall('GET', settings, false).join(' ')).not.toContain('up front');
  });
});
