import { create } from 'zustand';

type State = {
  authenticated: boolean;
};

type Action = {
  setAuthenticatedState: (authenticated: State['authenticated']) => void;
  reset: () => void;
};

const initialState: State = {
  authenticated: false,
};

const authStore = create<State & Action>((set) => ({
  ...initialState,
  setAuthenticatedState: (authenticated: boolean) => set({ authenticated }),
  reset: () => set(initialState),
}));

export const useAuthStore = authStore;
