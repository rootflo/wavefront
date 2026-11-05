const LAST_APP_KEY = 'wavefront-last-app';

export interface LastApp {
  id: string;
  /** When the app was last opened, in milliseconds since the epoch. */
  at: number;
}

/** Remembers, in this browser only, which app the user was last inside. */
export const saveLastApp = (id: string) => {
  try {
    localStorage.setItem(LAST_APP_KEY, JSON.stringify({ id, at: Date.now() } satisfies LastApp));
  } catch {
    // Storage can be blocked; the jump-back card then falls back to the most recently updated app.
  }
};

export const readLastApp = (): LastApp | null => {
  try {
    const raw = localStorage.getItem(LAST_APP_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LastApp>;
    return typeof parsed.id === 'string' && typeof parsed.at === 'number' ? { id: parsed.id, at: parsed.at } : null;
  } catch {
    return null;
  }
};
