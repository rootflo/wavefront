// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExtensionSlot } from './ExtensionSlot';
import { fetchRemotes, loadExtensions, type RemoteRuntime } from './loader';
import { renderHook } from '@testing-library/react';
import { registerNavItems, resetExtensions, useExtensionNavItems, useExtensionRegistry } from './registry';
import type { HostApi, RemoteDescriptor, RemoteModule } from './types';

const remote = (name: string): RemoteDescriptor => ({ name, entry: `https://x/${name}/remoteEntry.js` });

function fakeRuntime(modules: Record<string, RemoteModule | null | Error>): RemoteRuntime & { registered: string[] } {
  const registered: string[] = [];
  return {
    registered,
    register: (remotes) => registered.push(...remotes.map((r) => r.name)),
    load: async (name) => {
      const module = modules[name];
      if (module instanceof Error) throw module;
      return module ?? null;
    },
  };
}

beforeEach(() => resetExtensions());
afterEach(() => vi.restoreAllMocks());

describe('loadExtensions', () => {
  it('does nothing without remotes', async () => {
    const runtime = fakeRuntime({});
    expect(await loadExtensions([], runtime)).toEqual({ loaded: [], failed: [] });
    expect(runtime.registered).toEqual([]);
  });

  it('lets each remote register, tagged with its name', async () => {
    const runtime = fakeRuntime({
      access: {
        default: (host: HostApi) => {
          expect(host.version).toBe(1);
          host.registerRoutes([{ scope: 'app', path: 'access', element: <p>access page</p> }]);
          host.registerNavItems([{ id: 'access', name: 'Access', path: 'access', group: 'Security' }]);
          host.registerSlot('app.settings.access', () => <p>panel</p>);
        },
      },
    });

    const result = await loadExtensions([remote('access')], runtime);

    expect(result.loaded).toEqual(['access']);
    const state = useExtensionRegistry.getState();
    expect(state.routes.map((r) => [r.source, r.value.path])).toEqual([['access', 'access']]);
    expect(state.navItems[0].value.group).toBe('Security');
    expect(state.slots['app.settings.access']).toHaveLength(1);
  });

  it('skips a remote that fails and keeps the others', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const runtime = fakeRuntime({
      broken: new Error('404 remoteEntry.js'),
      empty: null,
      throws: {
        default: () => {
          throw new Error('register blew up');
        },
      },
      good: { default: (host) => host.registerNavItems([{ id: 'good', name: 'Good', path: 'good' }]) },
    });

    const result = await loadExtensions(['broken', 'empty', 'throws', 'good'].map(remote), runtime);

    expect(result.loaded).toEqual(['good']);
    expect(result.failed.map((f) => f.name).sort()).toEqual(['broken', 'empty', 'throws']);
    expect(useExtensionRegistry.getState().navItems).toHaveLength(1);
  });

  it('fails every remote when the runtime cannot register them', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const runtime: RemoteRuntime = {
      register: () => {
        throw new Error('no runtime');
      },
      load: vi.fn(),
    };
    const result = await loadExtensions([remote('a')], runtime);
    expect(result.failed.map((f) => f.name)).toEqual(['a']);
    expect(runtime.load).not.toHaveBeenCalled();
  });

  it('ignores a second nav item with a taken id', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const register = (host: HostApi) => host.registerNavItems([{ id: 'same', name: 'Same', path: 'same' }]);
    await loadExtensions(
      [remote('a'), remote('b')],
      fakeRuntime({ a: { default: register }, b: { default: register } })
    );
    expect(useExtensionRegistry.getState().navItems).toHaveLength(1);
  });
});

describe('useExtensionNavItems', () => {
  it('splits nav items by scope, defaulting to the app sidebar', () => {
    registerNavItems('iam', [
      { id: 'access', name: 'Access', path: 'access' },
      { id: 'iam', name: 'Identity & Access', path: 'iam', scope: 'console' },
    ]);
    const ids = (scope: 'app' | 'console') =>
      renderHook(() => useExtensionNavItems(scope)).result.current.map((item) => item.value.id);
    expect(ids('app')).toEqual(['access']);
    expect(ids('console')).toEqual(['iam']);
  });
});

describe('fetchRemotes', () => {
  const respond = (status: number, body: unknown) =>
    vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;

  it('reads the list the API returns', async () => {
    const fetchImpl = respond(200, { data: { extensions: [remote('a'), { name: 'no-entry' }] } });
    expect(await fetchRemotes(fetchImpl)).toEqual([remote('a')]);
  });

  it('treats an error response as no remotes', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(await fetchRemotes(respond(500, {}))).toEqual([]);
  });

  it('treats a network failure as no remotes', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('offline');
    }) as unknown as typeof fetch;
    expect(await fetchRemotes(fetchImpl)).toEqual([]);
  });
});

describe('ExtensionSlot', () => {
  it('renders nothing when no remote filled it', () => {
    const { container } = render(<ExtensionSlot name="app.settings.access" props={{ appId: 'a1' }} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders contributions with the slot props, isolating one that throws', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await loadExtensions(
      [remote('bad'), remote('ok')],
      fakeRuntime({
        bad: {
          default: (host) =>
            host.registerSlot('app.settings.access', () => {
              throw new Error('render failure');
            }),
        },
        ok: {
          default: (host) => host.registerSlot('app.settings.access', ({ appId }) => <p>access for {appId}</p>),
        },
      })
    );

    render(<ExtensionSlot name="app.settings.access" props={{ appId: 'a1' }} />);

    expect(screen.getByText('access for a1')).toBeTruthy();
  });
});
