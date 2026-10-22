import { Button } from '@app/components/ui/button';
import { cn } from '@app/lib/utils';
import React from 'react';

interface DetailActionsProps {
  /** Edit mode swaps Edit/Delete for Cancel/Save. */
  editing?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
  onSave?: () => void;
  onCancel?: () => void;
  saving?: boolean;
  saveDisabled?: boolean;
  cancelLabel?: string;
  /** Extra buttons that sit before Edit/Delete, e.g. Versions. */
  leading?: React.ReactNode;
  className?: string;
}

/**
 * The action buttons in a detail page's header, laid out the same everywhere:
 * Edit then Delete (Cancel then Save while editing), level with the page title.
 */
const DetailActions = ({
  editing = false,
  onEdit,
  onDelete,
  onSave,
  onCancel,
  saving,
  saveDisabled,
  cancelLabel = 'Cancel',
  leading,
  className,
}: DetailActionsProps) => (
  <div className={cn('flex shrink-0 items-center gap-2 sm:gap-3', className)}>
    {editing ? (
      <>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          {cancelLabel}
        </Button>
        <Button onClick={onSave} loading={saving} disabled={saveDisabled}>
          Save
        </Button>
      </>
    ) : (
      <>
        {leading}
        {onEdit && (
          <Button variant="outline" onClick={onEdit}>
            Edit
          </Button>
        )}
        {onDelete && (
          <Button variant="destructive" onClick={onDelete}>
            Delete
          </Button>
        )}
      </>
    )}
  </div>
);

export default DetailActions;
