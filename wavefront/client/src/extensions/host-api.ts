import { appEnv } from '@app/config/env';
import { TOKEN_KEY } from '@app/lib/constants';
import { registerNavItems, registerRoutes, registerSlot } from './registry';
import type { HostApi } from './types';

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** The API one remote registers through; everything it adds is tagged with its name. */
export function createHostApi(source: string): HostApi {
  return {
    version: 1,
    registerRoutes: (routes) => registerRoutes(source, routes),
    registerNavItems: (items) => registerNavItems(source, items),
    registerSlot: (name, component) => registerSlot(source, name, component),
    getAuthToken,
    consoleApiUrl: appEnv.baseURL,
  };
}
