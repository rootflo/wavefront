import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { isLiveStatus, shortAgo } from '@app/lib/app-status';
import { cn } from '@app/lib/utils';
import { formatAppName } from '@app/utils/string-formatting';
import { App } from '@app/types/app';
import dayjs from 'dayjs';
import { Check, Search } from 'lucide-react';
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
      <DialogContent className="flex h-[min(560px,calc(100dvh-2rem))] flex-col overflow-hidden sm:max-w-xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>Switch app</DialogTitle>
          <DialogDescription>
            {apps.length} {apps.length === 1 ? 'app' : 'apps'}. You stay on the same section in the one you pick.
          </DialogDescription>
        </DialogHeader>
        <div className="relative shrink-0">
          <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3.5 z-10 size-4 -translate-y-1/2" />
          <Input
            autoFocus
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && filteredApps.length) {
                e.preventDefault();
                onSelect(filteredApps[0]);
              }
            }}
            placeholder="Search by name or URL"
            aria-label="Search apps"
            className="h-10 rounded-[10px] pl-10 text-[13.5px]"
          />
        </div>

        <div className="-mx-3 min-h-0 flex-1 overflow-y-auto">
          {filteredApps.length === 0 ? (
            <p className="frost-text-muted px-3 py-10 text-center text-[13.5px]">No apps match “{search.trim()}”.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {filteredApps.map((app) => {
                const isSelected = selectedAppId === app.id;
                const displayName = formatAppName(app.app_name);
                const publicUrl = app.public_url?.replace(/^https?:\/\//, '');
                const live = isLiveStatus(app.status);
                return (
                  <li key={app.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(app)}
                      aria-current={isSelected ? 'true' : undefined}
                      className={cn(
                        'focus-visible:ring-brand/60 flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset',
                        isSelected ? 'bg-brand/10 ring-brand/30 ring-1 ring-inset' : 'hover:bg-frost-glass-strong'
                      )}
                    >
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#2f6df6,#8b5cf6)] text-sm font-extrabold text-white uppercase">
                        {displayName.charAt(0)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="frost-text block truncate text-[13.5px] font-semibold" title={displayName}>
                          {displayName}
                        </span>
                        <span className="frost-text-muted block truncate font-mono text-[11px]" title={app.public_url}>
                          {publicUrl || 'No public URL'}
                        </span>
                      </span>
                      <span className="frost-text-muted hidden shrink-0 flex-col items-end gap-1 text-[11px] font-medium sm:flex">
                        <span className="flex items-center gap-1.5 capitalize">
                          <span
                            className={cn('size-1.5 rounded-full', live ? 'bg-emerald-500' : 'bg-frost-text-subtle')}
                          />
                          {live ? 'Live' : app.status || 'Unknown'}
                        </span>
                        {app.created_at ? (
                          <span
                            className="frost-text-subtle"
                            title={dayjs(app.created_at).format('D MMM YYYY, h:mm A')}
                          >
                            Created {shortAgo(dayjs(app.created_at)).toLowerCase()}
                          </span>
                        ) : null}
                      </span>
                      {isSelected ? (
                        <Check className="text-brand size-4 shrink-0" aria-label="Current app" />
                      ) : (
                        <span className="size-4 shrink-0" aria-hidden />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SelectAppDialog;
