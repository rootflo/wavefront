// @vitest-environment jsdom
import { useNotifyStore } from '@app/store';
import { act, renderHook, waitFor } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatAttachments } from './use-chat-attachments';

/** A file input's change event carrying `files`. */
const pick = (...files: File[]) => {
  const input = document.createElement('input');
  input.type = 'file';
  Object.defineProperty(input, 'files', { value: files });
  return { target: input } as unknown as React.ChangeEvent<HTMLInputElement>;
};

const png = (name = 'chart.png') => new File(['pixels'], name, { type: 'image/png' });

describe('useChatAttachments', () => {
  beforeEach(() => useNotifyStore.getState().reset());

  it('reads picked images into base64 and reports them', async () => {
    const onAdded = vi.fn();
    const { result } = renderHook(() => useChatAttachments({ onAdded }));

    act(() => result.current.addImages(pick(png('a.png'), png('b.png'))));

    await waitFor(() => expect(result.current.images).toHaveLength(2));
    const [first] = result.current.images;
    expect(first.base64).toMatch(/^data:image\/png;base64,/);
    expect(first.base64Content).toBe(first.base64.split(',')[1]);
    expect(first.mimeType).toBe('image/png');
    expect(useNotifyStore.getState().message).toBe('2 image(s) uploaded successfully');
    expect(onAdded).toHaveBeenCalledTimes(1);
    expect(result.current.uploadingImage).toBe(false);
  });

  it('rejects the whole pick when one file is not allowed', async () => {
    const { result } = renderHook(() => useChatAttachments());

    act(() =>
      result.current.addImages(pick(png(), new File(['x'], 'notes.exe', { type: 'application/x-msdownload' })))
    );

    await waitFor(() => expect(useNotifyStore.getState().type).toBe('error'));
    expect(useNotifyStore.getState().message).toContain('notes.exe');
    expect(result.current.images).toHaveLength(0);
  });

  it('tags documents with their type for the API', async () => {
    const { result } = renderHook(() => useChatAttachments());

    act(() => result.current.addDocuments(pick(new File(['%PDF'], 'report.pdf', { type: 'application/pdf' }))));

    await waitFor(() => expect(result.current.documents).toHaveLength(1));
    expect(result.current.documents[0]).toMatchObject({
      mimeType: 'application/pdf',
      documentType: expect.any(String),
    });
  });

  it('removes one attachment, or clears them all after sending', async () => {
    const { result } = renderHook(() => useChatAttachments());
    act(() => result.current.addImages(pick(png('a.png'), png('b.png'))));
    await waitFor(() => expect(result.current.images).toHaveLength(2));

    act(() => result.current.removeImage(0));
    expect(result.current.images.map((image) => image.file.name)).toEqual(['b.png']);

    act(() => result.current.clear());
    expect(result.current.images).toHaveLength(0);
    expect(result.current.documents).toHaveLength(0);
  });
});
