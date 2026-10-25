import { describe, expect, it } from 'vitest';
import { parseJsonArray, parseJsonObject, parseOptionalNonNegativeInt } from './scheduled-job-form';

describe('scheduled job form parsing', () => {
  it('treats blank optional fields as unset', () => {
    expect(parseOptionalNonNegativeInt('  ', 'Offset')).toEqual({ ok: true, value: undefined });
    expect(parseJsonObject('', 'Params')).toEqual({ ok: true, value: undefined });
    expect(parseJsonArray('', 'Styles')).toEqual({ ok: true, value: undefined });
  });

  it('accepts whole numbers from zero up, and names the field when rejecting others', () => {
    expect(parseOptionalNonNegativeInt('0', 'Offset')).toEqual({ ok: true, value: 0 });
    expect(parseOptionalNonNegativeInt('25', 'Limit')).toEqual({ ok: true, value: 25 });
    expect(parseOptionalNonNegativeInt('-1', 'Offset')).toEqual({
      ok: false,
      error: 'Offset must be a non-negative integer',
    });
    expect(parseOptionalNonNegativeInt('2.5', 'Limit')).toMatchObject({ ok: false });
  });

  it('accepts only a JSON object for params', () => {
    expect(parseJsonObject('{"region": "eu"}', 'Params')).toEqual({ ok: true, value: { region: 'eu' } });
    expect(parseJsonObject('[1]', 'Params')).toEqual({ ok: false, error: 'Params must be a JSON object' });
    expect(parseJsonObject('null', 'Params')).toMatchObject({ ok: false });
    expect(parseJsonObject('{oops', 'Params')).toEqual({ ok: false, error: 'Params must be valid JSON (object)' });
  });

  it('accepts only a JSON array for column styles', () => {
    expect(parseJsonArray('[]', 'Styles')).toEqual({ ok: true, value: [] });
    expect(parseJsonArray('{}', 'Styles')).toEqual({ ok: false, error: 'Styles must be a JSON array' });
  });
});
