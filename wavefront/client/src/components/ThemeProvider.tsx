import { applyThemeClass, getMsUntilNextThemeBoundary, useThemeStore } from '@app/store/theme-store';
import { useEffect } from 'react';

/** Applies time-of-day theme on load and again at each 06:00 / 18:00 local boundary. */
const ThemeProvider = ({ children }: { children: React.ReactNode }) => {
  const theme = useThemeStore((state) => state.theme);
  const syncThemeToTimeOfDay = useThemeStore((state) => state.syncThemeToTimeOfDay);

  useEffect(() => {
    syncThemeToTimeOfDay();

    let timeoutId: ReturnType<typeof setTimeout>;

    const scheduleNextBoundary = () => {
      const delay = Math.max(getMsUntilNextThemeBoundary(), 1000);
      timeoutId = setTimeout(() => {
        syncThemeToTimeOfDay();
        scheduleNextBoundary();
      }, delay);
    };

    scheduleNextBoundary();

    return () => clearTimeout(timeoutId);
  }, [syncThemeToTimeOfDay]);

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  return children;
};

export default ThemeProvider;
