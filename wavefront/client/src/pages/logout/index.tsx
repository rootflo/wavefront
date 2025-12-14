import floConsoleService from '@app/api';
import { useAuthStore, useNotifyStore } from '@app/store';
import { useDashboardStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useNavigate } from 'react-router';

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
    localStorage.clear();
    queryClient.clear();
    navigate('/login');
  };

  const handleLogOut = async () => {
    try {
      await floConsoleService.consoleAuthService.logout();
    } catch (err) {
      console.log(err);
    } finally {
      onLogout();
    }
  };

  useEffect(() => {
    handleLogOut();
  }, []);

  return null;
};

export default Logout;
