import { useEffect } from 'react';

/**
 * Asks the browser to confirm before the tab is closed or reloaded while `active` is true.
 * In-app route changes are not covered: the app uses <BrowserRouter>, which has no useBlocker.
 */
export const useBeforeUnloadGuard = (active: boolean) => {
  useEffect(() => {
    if (!active) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Required by some browsers to trigger the native prompt.
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [active]);
};
