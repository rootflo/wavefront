import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark';

/** What the user picked: an explicit theme, or follow the OS setting. */
export type ThemePreference = ThemeMode | 'system';

/** Keep in sync with the inline pre-paint script in index.html. Not 'wavefront-theme': the old time-of-day code wrote that on every load, so it is not a real user choice. */
const THEME_STORAGE_KEY = 'wavefront-theme-preference';

const DARK_QUERY = '(prefers-color-scheme: dark)';

/** Browser UI color per theme; matches --frost-canvas. */
const THEME_COLOR: Record<ThemeMode, string> = { light: '#f6fafd', dark: '#0b1220' };

const readPreference = (): ThemePreference => {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
  } catch {
    // ignore
  }
  return 'system';
};

const writePreference = (preference: ThemePreference) => {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // ignore
  }
};

export const getSystemTheme = (): ThemeMode =>
  typeof window !== 'undefined' && window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light';

export const resolveTheme = (preference: ThemePreference): ThemeMode =>
  preference === 'system' ? getSystemTheme() : preference;

export const applyThemeClass = (theme: ThemeMode) => {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme]);
};

/** Calls back with the new OS theme whenever it changes; returns an unsubscribe function. */
export const subscribeToSystemTheme = (onChange: (theme: ThemeMode) => void) => {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
  const query = window.matchMedia(DARK_QUERY);
  const listener = (event: MediaQueryListEvent) => onChange(event.matches ? 'dark' : 'light');
  query.addEventListener('change', listener);
  return () => query.removeEventListener('change', listener);
};

/**
 * Switches instantly: suppresses transitions for one frame (see .theme-switching in index.css) so
 * elements with transition-colors don't each fade, which is slow over the blurred frost panels.
 */
const withoutTransitions = (apply: () => void) => {
  const root = document.documentElement;
  root.classList.add('theme-switching');
  apply();
  // Force a style flush so the new colors land while transitions are off
  void window.getComputedStyle(root).opacity;
  requestAnimationFrame(() => root.classList.remove('theme-switching'));
};

type ThemeState = {
  preference: ThemePreference;
  /** The theme actually applied, with 'system' resolved. */
  theme: ThemeMode;
  setPreference: (preference: ThemePreference) => void;
  toggleTheme: () => void;
  syncSystemTheme: () => void;
};

export const useThemeStore = create<ThemeState>((set, get) => {
  const preference = readPreference();
  const theme = resolveTheme(preference);
  if (typeof document !== 'undefined') {
    applyThemeClass(theme);
  }
  return {
    preference,
    theme,
    setPreference: (next) => {
      writePreference(next);
      const resolved = resolveTheme(next);
      withoutTransitions(() => applyThemeClass(resolved));
      set({ preference: next, theme: resolved });
    },
    toggleTheme: () => {
      get().setPreference(get().theme === 'dark' ? 'light' : 'dark');
    },
    syncSystemTheme: () => {
      if (get().preference !== 'system') return;
      const resolved = getSystemTheme();
      withoutTransitions(() => applyThemeClass(resolved));
      set({ theme: resolved });
    },
  };
});
