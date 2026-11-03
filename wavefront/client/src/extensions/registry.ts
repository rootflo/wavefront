import { useMemo } from 'react';
import { create } from 'zustand';
import type { ExtensionNavItem, ExtensionRoute, SlotComponent, SlotName } from './types';

/** A contribution, tagged with the remote that made it (for logs and isolation). */
export interface Contributed<T> {
  source: string;
  value: T;
}

interface RegistryState {
  routes: Contributed<ExtensionRoute>[];
  navItems: Contributed<ExtensionNavItem>[];
  slots: Partial<Record<SlotName, Contributed<SlotComponent>[]>>;
}

const empty = (): RegistryState => ({ routes: [], navItems: [], slots: {} });

/**
 * Everything remotes have contributed. A store rather than a module-level list
 * so the router, sidebar and slots re-render when a remote that loads late
 * registers.
 */
export const useExtensionRegistry = create<RegistryState>(() => empty());

export function registerRoutes(source: string, routes: ExtensionRoute[]) {
  useExtensionRegistry.setState((state) => ({
    routes: [...state.routes, ...routes.map((value) => ({ source, value }))],
  }));
}

export function registerNavItems(source: string, items: ExtensionNavItem[]) {
  useExtensionRegistry.setState((state) => {
    const taken = new Set(state.navItems.map((item) => item.value.id));
    const fresh = items.filter((item) => {
      if (taken.has(item.id)) {
        console.warn(`[extensions] ${source}: nav item '${item.id}' is already registered; ignored`);
        return false;
      }
      return true;
    });
    return { navItems: [...state.navItems, ...fresh.map((value) => ({ source, value }))] };
  });
}

export function registerSlot(source: string, name: SlotName, component: SlotComponent) {
  useExtensionRegistry.setState((state) => ({
    slots: { ...state.slots, [name]: [...(state.slots[name] ?? []), { source, value: component }] },
  }));
}

/** Drop every contribution (tests, and signing out). */
export function resetExtensions() {
  useExtensionRegistry.setState(empty());
}

export function useExtensionRoutes(scope: ExtensionRoute['scope']) {
  return useExtensionRegistry((state) => state.routes).filter((route) => route.value.scope === scope);
}

export function useExtensionNavItems(scope: NonNullable<ExtensionNavItem['scope']>) {
  const navItems = useExtensionRegistry((state) => state.navItems);
  // Memoised so callers can depend on the list without re-running every render.
  return useMemo(() => navItems.filter((item) => (item.value.scope ?? 'app') === scope), [navItems, scope]);
}

export function useSlotContributions(name: SlotName) {
  return useExtensionRegistry((state) => state.slots[name]) ?? [];
}
