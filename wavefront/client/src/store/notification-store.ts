import { create } from 'zustand';

export type TToastType = 'success' | 'error' | 'warning' | null;

type State = {
  visible: boolean;
  type: TToastType;
  message: string;
};

type Action = {
  notifySuccess: (message: State['message']) => void;
  notifyError: (message: State['message']) => void;
  notifyWarning: (message: State['message']) => void;
  reset: () => void;
};

const initialState: State = {
  visible: false,
  type: null,
  message: '',
};

const useNotificationStoreBase = create<State & Action>((set) => ({
  ...initialState,
  notifySuccess: (message: string) => set({ visible: true, type: 'success', message }),
  notifyError: (message: string) => set({ visible: true, type: 'error', message }),
  notifyWarning: (message: string) => set({ visible: true, type: 'warning', message }),
  reset: () => set(initialState),
}));

export const useNotifyStore = useNotificationStoreBase;
