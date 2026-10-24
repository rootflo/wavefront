import { useState } from 'react';
import { useParams } from 'react-router';

export type ListView = 'cards' | 'table';

// Each app and page keeps its own choice, e.g. one app's agents as cards while another's are a table.
const viewKey = (app: string, page: string) => `wavefront-list-view:${app}:${page}`;

const readView = (key: string): ListView => {
  try {
    return localStorage.getItem(key) === 'table' ? 'table' : 'cards';
  } catch {
    return 'cards';
  }
};

/** A listing page's cards-or-table choice, remembered in this browser per app and page. */
export const useListView = (page: string) => {
  const { app = '' } = useParams<{ app: string }>();
  const key = viewKey(app, page);
  // The app switcher can change the app without remounting the page, so a choice made here only
  // counts for the key it was made under; any other key reads its own saved choice.
  const [chosen, setChosen] = useState<{ key: string; view: ListView } | null>(null);
  const view = chosen?.key === key ? chosen.view : readView(key);

  const chooseView = (next: ListView) => {
    setChosen({ key, view: next });
    try {
      localStorage.setItem(key, next);
    } catch {
      // Storage can be blocked; the choice then lasts until the page reloads.
    }
  };

  return [view, chooseView] as const;
};
