// @vitest-environment jsdom
import { useNotifyStore } from '@app/store';
import { renderHookWithClient } from '@app/test/render';
import { act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useResourceMutation } from './use-resource-mutation';

const toast = () => useNotifyStore.getState();

describe('useResourceMutation', () => {
  beforeEach(() => useNotifyStore.getState().reset());

  it('toasts the success message and refetches the listed queries', async () => {
    const { result, client } = renderHookWithClient(() =>
      useResourceMutation({
        mutationFn: async (name: string) => name,
        successMessage: (_, name) => `Created ${name}`,
        errorMessage: 'Failed',
        invalidate: () => [['things', 'app-1'], false, undefined],
      })
    );
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    await act(() => result.current.mutateAsync('alpha'));

    expect(toast()).toMatchObject({ visible: true, type: 'success', message: 'Created alpha' });
    // Falsy keys (no app yet) are skipped rather than invalidating everything
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['things', 'app-1'] });
  });

  it("shows the server's message, falling back to the hook's own", async () => {
    const serverError = { response: { data: { meta: { error: 'Name already taken' } } } };
    const { result } = renderHookWithClient(() =>
      useResourceMutation({ mutationFn: () => Promise.reject(serverError), errorMessage: 'Failed to create' })
    );
    act(() => result.current.mutate());
    await waitFor(() => expect(toast().message).toBe('Name already taken'));

    const { result: bare } = renderHookWithClient(() =>
      useResourceMutation({ mutationFn: () => Promise.reject({}), errorMessage: 'Failed to create' })
    );
    act(() => bare.current.mutate());
    await waitFor(() => expect(toast().message).toBe('Failed to create'));
  });

  it('stays quiet on failure when the caller shows the error itself', async () => {
    const { result } = renderHookWithClient(() =>
      useResourceMutation({ mutationFn: () => Promise.reject(new Error('nope')), errorMessage: false })
    );
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toast().visible).toBe(false);
  });

  it('refetches after a failure too when asked', async () => {
    const { result, client } = renderHookWithClient(() =>
      useResourceMutation({
        mutationFn: () => Promise.reject(new Error('nope')),
        errorMessage: 'Failed',
        invalidate: () => [['connections']],
        invalidateOnError: true,
      })
    );
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    act(() => result.current.mutate());
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['connections'] }));
  });
});
