import AppsBackdrop from '@app/components/AppsBackdrop';
import AppCompactCard from './AppCompactCard';
import AppShowcaseCard from './AppShowcaseCard';
import AppsHero from './AppsHero';
import ColumnsToggle from './ColumnsToggle';
import { FilterSelect } from '@app/components/ListHeader';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Button } from '@app/components/ui/button';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { useDeleteApp, useGetAllApps, useGetCurrentUser } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { App } from '@app/types/app';
import { cn } from '@app/lib/utils';
import { formatAppName } from '@app/utils/string-formatting';
import { Box, Pin, Plus } from 'lucide-react';
import React, { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const COLUMNS_KEY = 'wavefront-apps-columns';
const PINNED_KEY = 'wavefront-pinned-apps';
const COLUMN_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8] as const;
// From this many per row the large cards would be too narrow, so small tiles take over.
const COMPACT_FROM = 5;
// Pointing at an app card tints the bottom of the page with that app's colour. Set to false to turn it off.
const AMBIENT_GLOW = false;

// Where the grid breaks, per choice of cards per row (one column on a phone whatever the choice).
const GRID_CLASS: Record<number, string> = {
  1: '',
  2: 'md:grid-cols-2',
  3: 'md:grid-cols-2 lg:grid-cols-3',
  4: 'md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
  5: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5',
  6: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6',
  7: 'grid-cols-2 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-7',
  8: 'grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8',
};

const readStored = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
};

const writeStored = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage can be blocked; the choice then just lasts for this visit.
  }
};

const Dashboard: React.FC = () => {
  const { data: apps = [], isLoading: appsLoading } = useGetAllApps(true);
  const { data: currentUser } = useGetCurrentUser(true);
  const navigate = useNavigate();
  const deleteApp = useDeleteApp();
  // Deletes and closes even when the delete fails
  const deletion = useDeleteConfirm<App>((item) =>
    deleteApp
      .mutateAsync({ appId: item.id, appName: item.app_name, deleteDeployment: item.deployment_type === 'auto' })
      .catch(() => undefined)
  );

  const { setSelectedApp } = useDashboardStore();

  const [columns, setColumns] = useState<number>(() => readStored(COLUMNS_KEY, 3));
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => readStored<string[]>(PINNED_KEY, []));
  const [glow, setGlow] = useState<{ tint: string; x: number } | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const sortedApps = useMemo(
    () =>
      [...apps].sort((a, b) =>
        formatAppName(a.app_name).localeCompare(formatAppName(b.app_name), undefined, { sensitivity: 'base' })
      ),
    [apps]
  );

  const statusOptions = useMemo(
    () => Array.from(new Set(sortedApps.map((app) => app.status).filter(Boolean))).sort(),
    [sortedApps]
  );

  const filteredApps = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return sortedApps.filter((app) => {
      if (statusFilter !== 'all' && app.status !== statusFilter) return false;
      if (!query) return true;
      return matchesSearch(query, app.app_name, app.public_url);
    });
  }, [sortedApps, searchTerm, statusFilter]);

  // Up to three apps keep a fixed showcase layout. Pinning and cards per row only matter once the list grows.
  const isFew = apps.length <= 3;
  const activeColumns = isFew ? (apps.length === 1 ? 1 : 3) : columns;
  const pinnedApps = isFew ? [] : filteredApps.filter((app) => pinnedIds.includes(app.id));
  const otherApps = isFew ? filteredApps : filteredApps.filter((app) => !pinnedIds.includes(app.id));
  const wide = activeColumns === 1;
  const compact = activeColumns >= COMPACT_FROM;
  const gridClass = cn('grid', compact ? 'gap-3' : 'gap-5', GRID_CLASS[activeColumns]);
  // A short list fills its first row with an invitation to add another app.
  const showAddTile = isFew && apps.length < 3;

  const renderCard = (app: App, index: number) =>
    compact ? (
      <AppCompactCard
        key={app.id}
        app={app}
        index={index}
        pinned={pinnedIds.includes(app.id)}
        onTogglePin={togglePin}
        onOpen={handleAppClick}
        onEditClick={(target) => navigate(`/apps/edit/${target.id}`)}
        onDeleteClick={(target) => deletion.ask(target)}
      />
    ) : (
      <AppShowcaseCard
        key={app.id}
        app={app}
        index={index}
        wide={wide}
        pinned={!isFew && pinnedIds.includes(app.id)}
        onTogglePin={isFew ? undefined : togglePin}
        onOpen={handleAppClick}
        onEditClick={(target) => navigate(`/apps/edit/${target.id}`)}
        onDeleteClick={(target) => deletion.ask(target)}
      />
    );

  const handleAppClick = (app: App, section = 'agents') => {
    navigate(`/apps/${app.id}/${section}`);
    setSelectedApp(app);
  };

  // Event delegation: whichever card the pointer is over sets the glow; leaving the cards clears it.
  const handleCardHover = (event: React.MouseEvent) => {
    if (!AMBIENT_GLOW || !window.matchMedia('(hover: hover)').matches) return;
    const card = (event.target as HTMLElement).closest<HTMLElement>('[data-tint]');
    const page = pageRef.current;
    if (!card || !page) {
      setGlow(null);
      return;
    }
    const cardBox = card.getBoundingClientRect();
    const pageBox = page.getBoundingClientRect();
    const x = Math.min(95, Math.max(5, ((cardBox.left + cardBox.width / 2 - pageBox.left) / pageBox.width) * 100));
    setGlow({ tint: card.dataset.tint ?? '47 109 246', x: Math.round(x) });
  };

  const chooseColumns = (next: number) => {
    setColumns(next);
    writeStored(COLUMNS_KEY, next);
  };

  const togglePin = (app: App) => {
    setPinnedIds((current) => {
      const next = current.includes(app.id) ? current.filter((id) => id !== app.id) : [...current, app.id];
      writeStored(PINNED_KEY, next);
      return next;
    });
  };

  const handleCreateApp = () => {
    navigate('/apps/create');
  };

  return (
    <div ref={pageRef} className="relative isolate h-full w-full overflow-hidden">
      <AppsBackdrop withGlow={AMBIENT_GLOW} glow={glow} />

      <div
        className={cn(
          'animate-fade-in relative mx-auto flex h-full w-full flex-col px-4 pt-6 pb-0 sm:px-8 sm:pt-10 md:px-12 lg:px-16',
          compact ? 'max-w-[1800px]' : 'max-w-7xl'
        )}
      >
        <AppsHero
          firstName={currentUser?.first_name}
          apps={sortedApps}
          onCreate={handleCreateApp}
          search={apps.length > 3 ? { value: searchTerm, onChange: setSearchTerm } : undefined}
          filters={
            apps.length > 3 && statusOptions.length > 1 ? (
              <FilterSelect
                label="Status"
                value={statusFilter}
                onValueChange={setStatusFilter}
                allValue="all"
                options={[{ value: 'all', label: 'All' }, ...statusOptions.map((value) => ({ value, label: value }))]}
              />
            ) : undefined
          }
          extras={
            !isFew ? (
              <ColumnsToggle value={columns} choices={COLUMN_CHOICES} onChange={chooseColumns} className="w-full" />
            ) : undefined
          }
        />

        <div
          className="no-scrollbar -mx-2 mt-4 min-h-0 flex-1 overflow-y-auto px-2 pt-3 pb-24 sm:pb-10"
          onMouseOver={handleCardHover}
          onMouseLeave={() => setGlow(null)}
        >
          {appsLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <ResourceCardSkeleton key={index} metadataCount={2} />
              ))}
            </div>
          ) : apps.length === 0 ? (
            <div className="frost-card ring-frost-border mx-auto mt-6 flex max-w-xl flex-col items-center gap-3 rounded-2xl border border-dashed p-8 text-center ring-1">
              <div className="bg-brand/12 text-brand flex size-14 items-center justify-center rounded-2xl">
                <Box className="size-6" />
              </div>
              <h2 className="frost-text text-lg font-semibold">Create your first app</h2>
              <p className="frost-text-muted max-w-sm text-sm">
                An app holds your agents, workflows, datasources and everything else for one project.
              </p>
              <Button className="mt-1 h-10 rounded-[10px] px-4 font-semibold" onClick={handleCreateApp}>
                <Plus className="size-4" strokeWidth={2.4} />
                Create app
              </Button>
            </div>
          ) : filteredApps.length === 0 ? (
            <p className="frost-text-muted py-10 text-center text-sm">No apps match your search.</p>
          ) : (
            <div className="flex flex-col gap-8">
              {pinnedApps.length > 0 ? (
                <section className="flex flex-col gap-3">
                  <h2 className="frost-text-muted flex items-center gap-2 text-xs font-semibold tracking-wider uppercase">
                    <Pin className="size-3.5" />
                    Pinned
                  </h2>
                  <div className={gridClass}>{pinnedApps.map(renderCard)}</div>
                </section>
              ) : null}
              <section className="flex flex-col gap-3">
                {pinnedApps.length > 0 && otherApps.length > 0 ? (
                  <h2 className="frost-text-muted text-xs font-semibold tracking-wider uppercase">All apps</h2>
                ) : null}
                {otherApps.length > 0 || showAddTile ? (
                  <div className={gridClass}>
                    {otherApps.map((app, index) => renderCard(app, index + pinnedApps.length))}
                    {showAddTile ? (
                      <button
                        type="button"
                        onClick={handleCreateApp}
                        className={cn(
                          'frost-text-muted hover:border-brand hover:bg-brand/10 hover:text-brand border-frost-border app-rise hidden min-h-72 cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[22px] border-[1.5px] border-dashed p-6 text-center transition-colors md:flex',
                          wide && 'min-h-36'
                        )}
                      >
                        <span className="frost-control ring-frost-border flex size-[52px] items-center justify-center rounded-2xl ring-1">
                          <Plus className="size-5" />
                        </span>
                        <span className="frost-text text-[15px] font-semibold">Add another app</span>
                        <span className="text-sm">Agents, workflows and data for a new project</span>
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </section>
            </div>
          )}
        </div>

        <DeleteConfirmationDialog
          {...deletion.dialogProps}
          title="Delete Application"
          message={`Are you sure you want to delete "${deletion.item?.app_name}"? This action cannot be undone and will remove all associated data.`}
        />
      </div>
    </div>
  );
};

export default Dashboard;
