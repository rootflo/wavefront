import { appEnv } from '@app/config/env';
import { getInstance, loadRemote, registerRemotes } from '@module-federation/runtime';
import { createHostApi, getAuthToken } from './host-api';
import type { RemoteDescriptor, RemoteModule } from './types';

/** The module every remote exposes; its default export registers the remote's UI. */
export const REGISTER_MODULE = 'register';

export interface LoadResult {
  loaded: string[];
  failed: { name: string; error: unknown }[];
}

/** The remotes this console should load. An empty list when none, or on any error. */
export async function fetchRemotes(fetchImpl: typeof fetch = fetch): Promise<RemoteDescriptor[]> {
  const token = getAuthToken();
  try {
    // Not the shared axios instance: a missing or failing extensions list is not
    // something to toast the user about.
    const response = await fetchImpl(`${appEnv.baseURL}/v1/settings/extensions`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      console.warn(`[extensions] listing remotes failed: HTTP ${response.status}`);
      return [];
    }
    const body = await response.json();
    const remotes = body?.data?.extensions;
    return Array.isArray(remotes) ? remotes.filter(isDescriptor) : [];
  } catch (error) {
    console.warn('[extensions] listing remotes failed', error);
    return [];
  }
}

function isDescriptor(value: unknown): value is RemoteDescriptor {
  const remote = value as RemoteDescriptor;
  return typeof remote?.name === 'string' && typeof remote?.entry === 'string';
}

export interface RemoteRuntime {
  register(remotes: RemoteDescriptor[]): void;
  load(name: string): Promise<RemoteModule | null>;
}

/** Module federation's runtime, set up by the host plugin in vite.config.ts. */
export const federationRuntime: RemoteRuntime = {
  register(remotes) {
    if (!getInstance()) throw new Error('module federation runtime is not initialised');
    registerRemotes(
      remotes.map((remote) => ({ name: remote.name, entry: remote.entry, type: remote.type ?? 'module' })),
      { force: true }
    );
  },
  load: (name) => loadRemote<RemoteModule>(`${name}/${REGISTER_MODULE}`),
};

/**
 * Load each remote and let it register its routes, nav items and slots.
 *
 * Remotes are independent: one that fails to fetch, evaluate or register is
 * logged and skipped, and the console carries on with the rest.
 */
export async function loadExtensions(
  remotes: RemoteDescriptor[],
  runtime: RemoteRuntime = federationRuntime
): Promise<LoadResult> {
  const result: LoadResult = { loaded: [], failed: [] };
  if (remotes.length === 0) return result;

  try {
    runtime.register(remotes);
  } catch (error) {
    console.error('[extensions] could not register remotes', error);
    return { loaded: [], failed: remotes.map((remote) => ({ name: remote.name, error })) };
  }

  await Promise.all(
    remotes.map(async (remote) => {
      try {
        const module = await runtime.load(remote.name);
        if (typeof module?.default !== 'function') {
          throw new Error(`'${remote.name}/${REGISTER_MODULE}' has no default register function`);
        }
        await module.default(createHostApi(remote.name));
        result.loaded.push(remote.name);
      } catch (error) {
        console.error(`[extensions] ${remote.name} failed to load; skipped`, error);
        result.failed.push({ name: remote.name, error });
      }
    })
  );
  return result;
}
