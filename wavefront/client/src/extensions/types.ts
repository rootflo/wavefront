import type { ComponentType, ReactNode, SVGProps } from 'react';

/**
 * The places in the console a remote can add UI to. A slot renders every
 * component registered for it, in registration order, each isolated so one
 * failing does not take the page (or the other contributions) down.
 */
export type SlotName =
  /** The app's edit page, below the app details. Props: { appId } */
  | 'app.settings.access'
  /** The agent detail page, beside the editor. Props: { appId, agentId } */
  | 'agent.detail.sidebar'
  /** The users page header, next to the page actions. Props: {} */
  | 'console.users.actions';

export type SlotProps = Record<string, string | undefined>;

export type SlotComponent = ComponentType<SlotProps>;

/** A page contributed by a remote. */
export interface ExtensionRoute {
  /**
   * 'app': a page inside an app, under /apps/:app/<path> with the app's sidebar.
   * 'console': a console page, under /<path> with the console chrome.
   */
  scope: 'app' | 'console';
  /** Relative to the scope, without a leading slash: 'access', 'access/:userId'. */
  path: string;
  element: ReactNode;
}

/** A navigation entry pointing at a route the remote registered. */
export interface ExtensionNavItem {
  /**
   * 'app' (default): an entry in each app's sidebar, for an 'app' route.
   * 'console': an entry in the console's account menu, beside Settings, for a
   * 'console' route -- for pages that are not about any one app.
   */
  scope?: 'app' | 'console';
  /** Unique across the console; also the first path segment the item is active on. */
  id: string;
  name: string;
  /** Relative to the scope: 'access' for /apps/:app/access, or 'iam' for /iam. */
  path: string;
  description?: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  /** Sidebar group title; a new title creates a group. Defaults to 'More'. Ignored for 'console'. */
  group?: string;
}

/** What the console hands a remote's `register` function. */
export interface HostApi {
  /** Bumped on breaking changes, so a remote can refuse an older console. */
  readonly version: 1;
  registerRoutes(routes: ExtensionRoute[]): void;
  registerNavItems(items: ExtensionNavItem[]): void;
  registerSlot(name: SlotName, component: SlotComponent): void;
  /** The signed-in user's console token, or null when signed out. */
  getAuthToken(): string | null;
  /** Base URL of the console API (ends in /floconsole). */
  readonly consoleApiUrl: string;
}

/** The module a remote exposes as './register'. */
export interface RemoteModule {
  default: (host: HostApi) => void | Promise<void>;
}

/** One remote, as GET /v1/settings/extensions lists it. */
export interface RemoteDescriptor {
  /** Module federation name of the remote; unique. */
  name: string;
  /** URL of the remote's entry (remoteEntry.js or mf-manifest.json). */
  entry: string;
  /** 'module' for ESM entries (the Vite plugin's default), else 'var'. */
  type?: 'module' | 'var';
}
