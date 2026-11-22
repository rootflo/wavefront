// @vitest-environment jsdom
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { useDeleteConfirm } from './use-delete-confirm';

type Item = { id: string; name: string };

/** A list row with a delete button, wired the way the list pages are. */
const Harness = ({ remove }: { remove: (item: Item) => Promise<unknown> }) => {
  const deletion = useDeleteConfirm<Item>(remove);
  return (
    <>
      <button onClick={() => deletion.ask({ id: '1', name: 'Alpha' })}>Delete Alpha</button>
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete thing"
        message={`Delete "${deletion.item?.name}"?`}
      />
    </>
  );
};

describe('useDeleteConfirm with DeleteConfirmationDialog', () => {
  it('asks first, deletes the chosen item on confirm, then closes', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    render(<Harness remove={remove} />);

    await userEvent.click(screen.getByText('Delete Alpha'));
    expect(screen.getByText('Delete "Alpha"?')).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(remove).toHaveBeenCalledWith({ id: '1', name: 'Alpha' });
    await waitFor(() => expect(screen.queryByText('Delete "Alpha"?')).not.toBeInTheDocument());
  });

  it('stays open when the delete fails, so it can be retried', async () => {
    const remove = vi.fn().mockRejectedValue(new Error('server down'));
    render(<Harness remove={remove} />);

    await userEvent.click(screen.getByText('Delete Alpha'));
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(remove).toHaveBeenCalled());
    expect(screen.getByText('Delete "Alpha"?')).toBeInTheDocument();
  });

  it('closes without deleting on cancel', async () => {
    const remove = vi.fn();
    render(<Harness remove={remove} />);

    await userEvent.click(screen.getByText('Delete Alpha'));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Delete "Alpha"?')).not.toBeInTheDocument());
    expect(remove).not.toHaveBeenCalled();
  });
});
