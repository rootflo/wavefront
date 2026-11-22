import { TOKEN_KEY } from '@app/lib/constants';
import Toast from './components/ui/toast';
import AppRouter from './router';
import { useAuthStore, useNotifyStore } from './store';
import { useMountEffect } from '@app/hooks/use-mount-effect';

function App() {
  const { setAuthenticatedState } = useAuthStore();
  const { visible, reset, type, message } = useNotifyStore();

  useMountEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) setAuthenticatedState(true);
    else setAuthenticatedState(false);
  });

  return (
    <div className="frost-canvas relative flex h-full w-full flex-col items-center justify-center">
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />
      <div className="relative flex h-full w-full flex-col items-center justify-center">
        <AppRouter />
      </div>
      <Toast visible={visible} reset={reset} type={type} message={message} />
    </div>
  );
}

export default App;
