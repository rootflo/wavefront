import { describe, expect, it } from 'vitest';
import { extractErrorMessage } from './errors';

// The axios interceptor toasts whatever this returns for every failed request
describe('extractErrorMessage', () => {
  it('reads the backend meta.error', () => {
    expect(extractErrorMessage({ response: { data: { meta: { error: 'Name already taken' } } } })).toBe(
      'Name already taken'
    );
  });

  it('joins FastAPI validation errors with their field names', () => {
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'name'], msg: 'field required' },
            { loc: ['body', 'config', 'port'], msg: 'must be a number' },
          ],
        },
      },
    };
    expect(extractErrorMessage(error)).toBe('name: field required; config.port: must be a number');
  });

  it('falls back to the error message when there is no response, as with a network failure', () => {
    expect(extractErrorMessage({ message: 'Network Error', response: undefined })).toBe('Network Error');
  });

  it('returns undefined for values that are not errors', () => {
    expect(extractErrorMessage(undefined)).toBeUndefined();
    expect(extractErrorMessage('boom')).toBeUndefined();
  });
});
