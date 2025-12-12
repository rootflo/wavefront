import { TOKEN_KEY } from "@app/lib/constants";
import { useEffect } from "react";
import AppRouter from "./router";
import { useAuthStore, useNotifyStore } from "./store";
import Toast from "./components/ui/toast";

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
