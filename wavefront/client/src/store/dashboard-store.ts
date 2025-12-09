import { create } from 'zustand';
import { App } from '@app/types/app';

type State = {
  selectedApp: App | null;
};

type Action = {
  setSelectedApp: (selectedApp: State['selectedApp']) => void;
  reset: () => void;
};

const initialState: State = {
  selectedApp: null,
};

const dashboardStore = create<State & Action>((set) => ({
  ...initialState,
  setSelectedApp: (selectedApp: State['selectedApp']) => set({ selectedApp }),
  reset: () => set(initialState),
}));

export const useDashboardStore = dashboardStore;
