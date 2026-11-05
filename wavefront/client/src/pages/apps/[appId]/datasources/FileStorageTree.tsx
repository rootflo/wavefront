import { cn } from '@app/lib/utils';
import { DatasourceFolderEntry } from '@app/types/datasource';
import { ChevronRight, Folder, FolderOpen, Loader2 } from 'lucide-react';

import { FolderState } from './file-storage';

/** One folder in the panel's folder tree, with its loaded sub-folders below it when expanded. */
export const TreeFolder = ({
  folder,
  depth,
  selected,
  expanded,
  cache,
  onSelect,
  onToggle,
}: {
  folder: DatasourceFolderEntry;
  depth: number;
  selected: string;
  expanded: Set<string>;
  cache: Record<string, FolderState>;
  onSelect: (prefix: string) => void;
  onToggle: (prefix: string) => void;
}) => {
  const state = cache[folder.prefix];
  const open = expanded.has(folder.prefix);
  // Until it's loaded we can't know, so offer the chevron; once loaded, only if it has sub-folders.
  const mayHaveChildren = !state?.loaded || state.folders.length > 0;
  const isSelected = selected === folder.prefix;
  const FolderIcon = open && state?.folders.length ? FolderOpen : Folder;
  return (
    <li>
      <div
        className={cn(
          'flex items-center gap-1 rounded-md py-1 pr-2 text-sm transition-colors',
          isSelected ? 'bg-brand/12 text-brand font-medium' : 'frost-text hover:bg-frost-glass'
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        <button
          type="button"
          aria-label={open ? `Collapse ${folder.name}` : `Expand ${folder.name}`}
          aria-expanded={mayHaveChildren ? open : undefined}
          onClick={() => onToggle(folder.prefix)}
          className={cn(
            'frost-text-subtle hover:text-frost-text flex size-5 shrink-0 items-center justify-center rounded',
            mayHaveChildren ? 'cursor-pointer' : 'invisible'
          )}
        >
          {open && state?.loading && !state.loaded ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
          )}
        </button>
        <button
          type="button"
          onClick={() => onSelect(folder.prefix)}
          title={folder.prefix}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
        >
          <FolderIcon className={cn('size-4 shrink-0', isSelected ? 'text-brand' : 'text-amber-500')} />
          <span className="truncate">{folder.name}</span>
        </button>
      </div>
      {open && state?.folders.length ? (
        <ul>
          {state.folders.map((child) => (
            <TreeFolder
              key={child.prefix}
              folder={child}
              depth={depth + 1}
              selected={selected}
              expanded={expanded}
              cache={cache}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
};

/**
 * A storage browser like a cloud console's: the folder tree on the left, the open folder's contents on the right,
 * with upload, preview, download and delete. Each folder is fetched one level at a time from `files/browse` the
 * first time it is opened or expanded, then kept until a refresh.
 */
