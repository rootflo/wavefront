import { useEffect } from 'react';

/**
 * Runs `effect` once, after the first render, with the values it saw then. For start-up work such as
 * auth checks and redirects, which must not re-run when `navigate` or the location change.
 */
export const useMountEffect = (effect: () => void | (() => void)) => {
  // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once by design; that's this hook's purpose
  useEffect(effect, []);
};
