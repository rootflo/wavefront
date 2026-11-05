import { useState } from 'react';

/** The outcome of the last connection test, kept in this browser so the status survives a reload. */
export interface ConnectionTest {
  ok: boolean;
  /** Milliseconds since the epoch. */
  at: number;
}

const storageKey = (datasourceId: string) => `wavefront-datasource-test:${datasourceId}`;

const readTest = (datasourceId: string): ConnectionTest | null => {
  try {
    const raw = localStorage.getItem(storageKey(datasourceId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ConnectionTest>;
    return typeof parsed.ok === 'boolean' && typeof parsed.at === 'number' ? { ok: parsed.ok, at: parsed.at } : null;
  } catch {
    return null;
  }
};

export const useConnectionTest = (datasourceId: string | undefined) => {
  const [test, setTest] = useState<ConnectionTest | null>(() => (datasourceId ? readTest(datasourceId) : null));

  const recordTest = (ok: boolean) => {
    const next = { ok, at: Date.now() };
    setTest(next);
    if (!datasourceId) return;
    try {
      localStorage.setItem(storageKey(datasourceId), JSON.stringify(next));
    } catch {
      // Storage can be blocked; the status then lasts until the page reloads.
    }
  };

  return [test, recordTest] as const;
};
