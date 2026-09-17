import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark';

const THEME_STORAGE_KEY = 'wavefront-theme';

/** Theme flips at 06:00 (light) and 18:00 (dark) local time. */
export const THEME_SWITCH_HOURS = [6, 18] as const;

/** Dark from 6pm–5:59am local time; light otherwise. */
export const getThemeForTimeOfDay = (date = new Date()): ThemeMode => {
  const hour = date.getHours();
  return hour >= 18 || hour < 6 ? 'dark' : 'light';
};

/** Milliseconds until the next 06:00 or 18:00 local boundary. */
export const getMsUntilNextThemeBoundary = (date = new Date()): number => {
  const candidates = THEME_SWITCH_HOURS.map((hour) => {
    const boundary = new Date(date);
    boundary.setHours(hour, 0, 0, 0);
    if (boundary.getTime() <= date.getTime()) {
      boundary.setDate(boundary.getDate() + 1);
    }
    return boundary.getTime();
  });

  return Math.min(...candidates) - date.getTime();
};

export const applyThemeClass = (theme: ThemeMode) => {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
};

type ThemeState = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  syncThemeToTimeOfDay: () => void;
};

export const useThemeStore = create<ThemeState>((set, get) => {
  const theme = getThemeForTimeOfDay();
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // ignore
  }
  if (typeof document !== 'undefined') {
    applyThemeClass(theme);
  }
  return {
    theme,
    setTheme: (next) => {
      try {
        localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // ignore
      }
      applyThemeClass(next);
      set({ theme: next });
    },
    toggleTheme: () => {
      const next = get().theme === 'dark' ? 'light' : 'dark';
      get().setTheme(next);
    },
    syncThemeToTimeOfDay: () => {
      get().setTheme(getThemeForTimeOfDay());
    },
  };
});
