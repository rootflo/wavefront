import floConsoleService from '@app/api';
import { clearSession } from '@app/lib/session';
import { useAuthStore, useNotifyStore } from '@app/store';
import { useDashboardStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { useMountEffect } from '@app/hooks/use-mount-effect';

const resetAllStores = () => {
  useAuthStore.getState().reset();
  useNotifyStore.getState().reset();
  useDashboardStore.getState().reset();
};

const Logout = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const onLogout = () => {
    resetAllStores();
    clearSession();
    queryClient.clear();
    navigate('/login');
  };

  const handleLogOut = async () => {
    try {
      await floConsoleService.consoleAuthService.logout();
    } catch {
      // The local session ends whether or not the server heard about it
    } finally {
      onLogout();
    }
  };

  useMountEffect(() => {
    handleLogOut();
  });

  return null;
};

export default Logout;
