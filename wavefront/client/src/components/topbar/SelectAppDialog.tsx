import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { cn, formatAppName } from '@app/lib/utils';
import { App } from '@app/types/app';
import dayjs from 'dayjs';
import React, { useEffect, useMemo, useState } from 'react';

interface SelectAppDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apps: App[];
  selectedAppId?: string | null;
  onSelect: (app: App) => void;
}

const SelectAppDialog: React.FC<SelectAppDialogProps> = ({ open, onOpenChange, apps, selectedAppId, onSelect }) => {
  const [search, setSearch] = useState('');

  const sortedApps = useMemo(
    () =>
      [...apps].sort((a, b) =>
        formatAppName(a.app_name).localeCompare(formatAppName(b.app_name), undefined, { sensitivity: 'base' })
      ),
    [apps]
  );

  const filteredApps = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sortedApps;
    return sortedApps.filter((app) => {
      const name = formatAppName(app.app_name).toLowerCase();
      const url = (app.public_url || '').toLowerCase();
      return name.includes(query) || url.includes(query) || app.app_name.toLowerCase().includes(query);
    });
  }, [sortedApps, search]);

  useEffect(() => {
    if (!open) setSearch('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="flex h-[520px] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="border-frost-border flex shrink-0 items-center justify-between gap-4 border-b px-6 py-4">
          <DialogHeader className="space-y-0 text-left">
            <DialogTitle>Select App</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search apps"
            className="h-8 w-[200px] shrink-0"
          />
        </div>

        <div className="frost-table-panel ring-frost-border m-4 mb-0 min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          {filteredApps.length === 0 ? (
            <p className="frost-text-muted px-3 py-8 text-center text-[13px]">No apps found</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Created At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredApps.map((app) => {
                  const isSelected = selectedAppId === app.id;
                  return (
                    <TableRow key={app.id} className={cn(isSelected && 'bg-frost-glass-strong')}>
                      <TableCell
                        className="max-w-[200px] cursor-pointer truncate lowercase underline"
                        title={app.app_name}
                        onClick={() => onSelect(app)}
                      >
                        {formatAppName(app.app_name)}
                      </TableCell>
                      <TableCell className="frost-text-muted max-w-[280px] truncate" title={app.public_url}>
                        {app.public_url || '—'}
                      </TableCell>
                      <TableCell className="frost-text-muted capitalize">
                        {dayjs(app.created_at).format('DD/MM/YYYY HH:mm A') || '—'}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>

        <DialogFooter className="border-frost-border shrink-0 border-t px-6 py-4 sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SelectAppDialog;
