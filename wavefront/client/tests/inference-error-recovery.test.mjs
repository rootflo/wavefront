import assert from 'node:assert/strict';
import test from 'node:test';

import { recoverFailedInference, runInferenceWithRecovery } from '../src/lib/inference-error-recovery.js';

function makeRecoveryState(errorMessage) {
  const state = {
    history: [{ role: 'assistant', content: 'Earlier answer' }],
    input: 'try again with these details',
    images: [{ name: 'diagram.png' }],
    documents: [{ name: 'notes.pdf' }],
    errors: [],
  };
  const originalHistory = state.history;

  return {
    state,
    originalHistory,
    recovery: {
      historyBeforeRequest: originalHistory,
      inputBeforeRequest: state.input,
      getErrorMessage: () => errorMessage,
      setChatHistory: (history) => {
        state.history = history;
      },
      setInferenceInput: (input) => {
        state.input = input;
      },
      clearUploadedImages: () => {
        state.images = [];
      },
      clearUploadedDocuments: () => {
        state.documents = [];
      },
      notifyError: (message) => {
        state.errors.push(message);
      },
    },
  };
}

test('a failed request rolls optimistic messages back to the prior chat history', () => {
  const previousHistory = [{ role: 'assistant', content: 'Earlier answer' }];
  const rejectedHistory = [
    ...previousHistory,
    { role: 'user', content: { document_base64: 'blocked-by-server' } },
    { role: 'user', content: 'Hello' },
  ];

  const recovery = recoverFailedInference(previousHistory, 'Request failed', 'retry me');

  assert.deepEqual(rejectedHistory.slice(0, recovery.history.length), recovery.history);
  assert.deepEqual(recovery.history, previousHistory);
  assert.equal(recovery.input, 'retry me');
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

test('an invalid-file inference failure restores page state and clears both attachment types', async () => {
  const { state, originalHistory, recovery } = makeRecoveryState('Invalid file format at position 0.');
  const outcome = await runInferenceWithRecovery(
    async () => {
      throw new Error('server rejected file');
    },
    recovery
  );

  assert.equal(outcome.success, false);
  assert.deepEqual(state.history, originalHistory);
  assert.equal(state.input, 'try again with these details');
  assert.deepEqual(state.images, []);
  assert.deepEqual(state.documents, []);
  assert.deepEqual(state.errors, ['Invalid file format at position 0.']);
});

test('a transient inference failure restores text and chat but keeps attachments and shows its error', async () => {
  const { state, originalHistory, recovery } = makeRecoveryState('Service unavailable');
  const images = state.images;
  const documents = state.documents;
  const outcome = await runInferenceWithRecovery(
    async () => {
      throw new Error('network failed');
    },
    recovery
  );

  assert.equal(outcome.success, false);
  assert.deepEqual(state.history, originalHistory);
  assert.equal(state.input, 'try again with these details');
  assert.equal(state.images, images);
  assert.equal(state.documents, documents);
  assert.deepEqual(state.errors, ['Service unavailable']);
});

test('a successful inference request returns its result without changing recovery state', async () => {
  const { state, recovery } = makeRecoveryState('unused');
  const outcome = await runInferenceWithRecovery(async () => 'answer', recovery);

  assert.deepEqual(outcome, { success: true, value: 'answer' });
  assert.equal(state.errors.length, 0);
  assert.equal(state.images.length, 1);
  assert.equal(state.documents.length, 1);
});
