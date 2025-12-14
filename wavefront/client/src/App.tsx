import { TOKEN_KEY } from '@app/lib/constants';
import { useEffect } from 'react';
import Toast from './components/ui/toast';
import AppRouter from './router';
import { useAuthStore, useNotifyStore } from './store';

function App() {
  const { setAuthenticatedState } = useAuthStore();
  const { visible, reset, type, message } = useNotifyStore();

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) setAuthenticatedState(true);
    else setAuthenticatedState(false);
  }, []);

  return (
    <div className="flex h-full w-screen flex-col items-center justify-center bg-white">
      <AppRouter />
      <Toast visible={visible} reset={reset} type={type} message={message} />
    </div>
  );
}

export default App;
