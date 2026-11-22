import { create } from 'zustand';
import { App } from '@app/types/app';

type State = {
  selectedApp: App | null;
  // Phone-only: the workspace menu opens as a drawer from the top bar.
  mobileNavOpen: boolean;
};

type Action = {
  setSelectedApp: (selectedApp: State['selectedApp']) => void;
  setMobileNavOpen: (open: boolean) => void;
  reset: () => void;
};

const initialState: State = {
  selectedApp: null,
  mobileNavOpen: false,
};

const dashboardStore = create<State & Action>((set) => ({
  ...initialState,
  setSelectedApp: (selectedApp: State['selectedApp']) => set({ selectedApp }),
  setMobileNavOpen: (mobileNavOpen: boolean) => set({ mobileNavOpen }),
  reset: () => set(initialState),
}));

export const useDashboardStore = dashboardStore;
