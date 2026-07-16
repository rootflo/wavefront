import * as React from 'react';
import dayjs from 'dayjs';

import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { EntityVersion } from '@app/types/version';

interface VersionsDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Human label for the entity, e.g. "agent" or "workflow". */
  entityLabel: string;
  versions: EntityVersion[];
  loading?: boolean;
  /** Version currently being viewed in the parent (highlighted). */
  selectedVersion?: number;
  onView: (version: number) => void;
  onPromote: (version: number) => void;
  onDelete: (version: number) => void;
  /** Disables actions while a promote/delete mutation is in flight. */
  actionPending?: boolean;
}

const formatDate = (dateString?: string) => {
  if (!dateString) return '-';
  return dayjs(dateString).format('DD MMM YYYY hh:mm A');
};

const VersionsDialog: React.FC<VersionsDialogProps> = ({
  isOpen,
  onOpenChange,
  entityLabel,
  versions,
  loading = false,
  selectedVersion,
  onView,
  onPromote,
  onDelete,
  actionPending = false,
}) => {
  const [deleteTarget, setDeleteTarget] = React.useState<number | null>(null);

  const sortedVersions = React.useMemo(() => [...versions].sort((a, b) => a.version - b.version), [versions]);

  const handleDeleteConfirm = () => {
    if (deleteTarget !== null) {
      onDelete(deleteTarget);
      setDeleteTarget(null);
    }
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Versions</DialogTitle>
            <DialogDescription>
              View, promote, or delete versions of this {entityLabel}. Promoting a version makes it the one served by
              default; new versions are never promoted automatically.
            </DialogDescription>
          </DialogHeader>

          {loading ? (
            <div className="flex items-center justify-center py-8 text-sm text-gray-500">Loading versions...</div>
          ) : sortedVersions.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-gray-500">No versions found</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedVersions.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">v{v.version}</span>
                        {v.is_current && <Badge variant="default">Current</Badge>}
                        {selectedVersion === v.version && !v.is_current && <Badge variant="secondary">Viewing</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="text-gray-600">{formatDate(v.created_at)}</TableCell>
                    <TableCell className="text-gray-600">{formatDate(v.updated_at)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => onView(v.version)}>
                          View
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={v.is_current || actionPending}
                          onClick={() => onPromote(v.version)}
                        >
                          Promote
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={v.is_current || actionPending}
                          onClick={() => setDeleteTarget(v.version)}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        title="Delete Version"
        message={`Are you sure you want to delete version ${deleteTarget}? This cannot be undone and the version number will not be reused.`}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
        loading={actionPending}
      />
    </>
  );
};

export default VersionsDialog;
