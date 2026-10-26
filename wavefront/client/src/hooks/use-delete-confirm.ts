import React, { useState } from 'react';

/**
 * State for a "delete this?" confirmation. Spread `dialogProps` onto DeleteConfirmationDialog, which shows its
 * own spinner while `remove` runs. The dialog closes once `remove` resolves and stays open if it rejects, since
 * the mutation hook has already reported the error.
 */
export const useDeleteConfirm = <T>(remove: (item: T) => Promise<unknown>) => {
  const [item, setItem] = useState<T | null>(null);

  return {
    /** The item awaiting confirmation, for the dialog's message. */
    item,
    /** Asks to delete `target`. Pass the click event when the button sits inside a clickable card. */
    ask: (target: T, event?: React.MouseEvent) => {
      event?.stopPropagation();
      setItem(target);
    },
    dialogProps: {
      isOpen: item !== null,
      onCancel: () => setItem(null),
      onConfirm: async () => {
        if (item === null) return;
        try {
          await remove(item);
          setItem(null);
        } catch {
          // Already reported by the mutation hook; leave the dialog open to retry
        }
      },
    },
  };
};
