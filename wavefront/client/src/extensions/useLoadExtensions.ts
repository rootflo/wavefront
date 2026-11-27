import { useEffect } from 'react';
import { fetchRemotes, loadExtensions } from './loader';
import { resetExtensions } from './registry';

/** Load the console's remotes once the user is signed in; forget them on sign-out. */
export function useLoadExtensions(authenticated: boolean | undefined) {
  useEffect(() => {
    if (!authenticated) {
      resetExtensions();
      return;
    }
    let cancelled = false;
    fetchRemotes().then((remotes) => {
      if (!cancelled) void loadExtensions(remotes);
    });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);
}
