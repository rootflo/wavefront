// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FileUploadDialog from './FileUploadDialog';

const uploadFilesBatch = vi.fn();
vi.mock('@app/api', () => ({
  default: { datasourcesService: { uploadFilesBatch: (...args: unknown[]) => uploadFilesBatch(...args) } },
}));

const picked = (relativePath: string) => ({ file: new File(['data'], relativePath.split('/').pop()!), relativePath });

const renderDialog = (props: Partial<React.ComponentProps<typeof FileUploadDialog>> = {}) => {
  const handlers = { onOpenChange: vi.fn(), onUploaded: vi.fn() };
  render(
    <FileUploadDialog
      open
      datasourceId="ds-1"
      targetPrefix="reports/"
      existingFileNames={[]}
      initialFiles={[picked('q1.csv'), picked('2024/q2.csv')]}
      {...handlers}
      {...props}
    />
  );
  return handlers;
};

describe('FileUploadDialog', () => {
  beforeEach(() => uploadFilesBatch.mockReset());

  it('uploads the dropped files into the target folder, keeping sub-folder paths, then closes', async () => {
    uploadFilesBatch.mockResolvedValue({ data: { data: { results: [{ index: 0 }, { index: 1 }] } } });
    const { onOpenChange, onUploaded } = renderDialog();

    expect(screen.getByText('q1.csv')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    const [datasourceId, items] = uploadFilesBatch.mock.calls[0];
    expect(datasourceId).toBe('ds-1');
    expect(items.map((item: { path: string }) => item.path)).toEqual(['reports/q1.csv', 'reports/2024/q2.csv']);
    expect(onUploaded).toHaveBeenCalledWith('reports/');
  });

  it('stays open showing which files failed, and offers to retry just those', async () => {
    uploadFilesBatch.mockResolvedValue({
      data: { data: { results: [{ index: 0 }, { index: 1, error: 'File too large' }] } },
    });
    const { onOpenChange, onUploaded } = renderDialog();

    await userEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }));

    expect(await screen.findByText('File too large')).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    // One file did go up, so the folder listing should refresh
    expect(onUploaded).toHaveBeenCalledWith('reports/');

    uploadFilesBatch.mockResolvedValue({ data: { data: { results: [{ index: 0 }] } } });
    await userEvent.click(screen.getByRole('button', { name: /Retry failed/ }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    // Only the failed file is sent again
    expect(uploadFilesBatch.mock.calls[1][1].map((item: { path: string }) => item.path)).toEqual([
      'reports/2024/q2.csv',
    ]);
  });

  it('marks a file that would replace one already in the folder', () => {
    renderDialog({ existingFileNames: ['q1.csv'], initialFiles: [picked('q1.csv')] });
    expect(screen.getByText(/replaces/i)).toBeInTheDocument();
  });
});
