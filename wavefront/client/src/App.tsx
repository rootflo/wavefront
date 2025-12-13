import { TOKEN_KEY } from '@app/lib/constants';
import { useEffect } from 'react';
import AppRouter from './router';
import { useAuthStore } from './store';

function App() {
  const { setAuthenticatedState } = useAuthStore();

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) setAuthenticatedState(true);
    else setAuthenticatedState(false);
  }, []);

  return (
    <div className="flex h-full w-screen flex-col items-center justify-center bg-white">
      <AppRouter />
    </div>
  );
}

export default App;
