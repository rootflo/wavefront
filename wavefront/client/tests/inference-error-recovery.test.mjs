import assert from 'node:assert/strict';
import test from 'node:test';

import { recoverFailedInference } from '../src/lib/inference-error-recovery.js';

test('a failed request rolls optimistic messages back to the prior chat history', () => {
  const previousHistory = [{ role: 'assistant', content: 'Earlier answer' }];
  const rejectedHistory = [
    ...previousHistory,
    { role: 'user', content: { document_base64: 'blocked-by-server' } },
    { role: 'user', content: 'Hello' },
  ];

  const recovery = recoverFailedInference(previousHistory, 'Request failed');

  assert.deepEqual(rejectedHistory.slice(0, recovery.history.length), recovery.history);
  assert.deepEqual(recovery.history, previousHistory);
  assert.equal(recovery.clearAttachments, false);
});

test('an invalid-file rejection also clears pending attachments', () => {
  const previousHistory = [{ role: 'assistant', content: 'Earlier answer' }];

  const recovery = recoverFailedInference(previousHistory, 'Invalid file format at position 0.');

  assert.deepEqual(recovery.history, previousHistory);
  assert.equal(recovery.clearAttachments, true);
});

test('transient failures preserve pending attachments for a retry', () => {
  const recovery = recoverFailedInference([], 'Network error');

  assert.equal(recovery.clearAttachments, false);
});
