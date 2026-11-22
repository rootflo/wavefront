import { matchPath } from 'react-router';

/**
 * Pages directly under /apps that are not an app, so their segment is never an app ID.
 * Keep in sync with the top-level /apps/* routes in router/routes.tsx.
 */
const NON_APP_SEGMENTS = new Set(['users', 'create', 'edit']);

/** The app the current page belongs to (the `:app` in /apps/:app/...), or undefined outside one. */
export const getRouteAppId = (pathname: string = window.location.pathname): string | undefined => {
  const app = matchPath({ path: '/apps/:app', end: false }, pathname)?.params.app;
  return app && !NON_APP_SEGMENTS.has(app) ? app : undefined;
};
