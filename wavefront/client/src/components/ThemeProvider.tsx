import { applyThemeClass, subscribeToSystemTheme, useThemeStore } from '@app/store/theme-store';
import { useEffect } from 'react';

/** Applies the saved theme, and follows OS theme changes while the preference is 'system'. */
const ThemeProvider = ({ children }: { children: React.ReactNode }) => {
  const theme = useThemeStore((state) => state.theme);
  const syncSystemTheme = useThemeStore((state) => state.syncSystemTheme);

  useEffect(() => subscribeToSystemTheme(syncSystemTheme), [syncSystemTheme]);

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  return children;
};

export default ThemeProvider;
