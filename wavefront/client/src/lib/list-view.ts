import { useState } from 'react';

export type ListView = 'cards' | 'table';

// One choice for every Build page, so moving between agents, workflows and the rest keeps the same layout.
const VIEW_KEY = 'wavefront-build-list-view';

const readView = (): ListView => {
  try {
    return localStorage.getItem(VIEW_KEY) === 'table' ? 'table' : 'cards';
  } catch {
    return 'cards';
  }
};

/** The Build pages' cards-or-table choice, remembered in this browser. */
export const useListView = () => {
  const [view, setView] = useState<ListView>(readView);

  const chooseView = (next: ListView) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Storage can be blocked; the choice then lasts until the page reloads.
    }
  };

  return [view, chooseView] as const;
};
