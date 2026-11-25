import { describe, expect, it } from 'vitest';
import { contextFromRows, MAX_CONTEXT_BYTES } from './outbound-call-context';

describe('contextFromRows', () => {
  it('builds the context from filled rows and skips blank ones', () => {
    expect(
      contextFromRows([
        { key: 'reason_for_call', value: ' overdue bill ' },
        { key: '', value: '' },
        { key: 'customer_name', value: 'Jane Doe' },
      ])
    ).toEqual({ context: { reason_for_call: 'overdue bill', customer_name: 'Jane Doe' } });
  });

  it('sends nothing when every row is blank', () => {
    expect(contextFromRows([{ key: '', value: '' }])).toEqual({});
  });

  it('rejects keys the API rejects', () => {
    expect(contextFromRows([{ key: 'Reason For Call', value: 'x' }]).error).toContain('lowercase');
    expect(contextFromRows([{ key: '', value: 'x' }]).error).toContain('(empty)');
  });

  it('rejects a key used twice', () => {
    const rows = [
      { key: 'a', value: '1' },
      { key: 'a', value: '2' },
    ];
    expect(contextFromRows(rows).error).toContain('used twice');
  });

  it('rejects context over the size limit', () => {
    expect(contextFromRows([{ key: 'notes', value: 'x'.repeat(MAX_CONTEXT_BYTES) }]).error).toContain('over');
  });
});
