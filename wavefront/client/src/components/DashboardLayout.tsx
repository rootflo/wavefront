import Topbar from '@app/components/topbar/Topbar';
import { CURRENT_PATH_KEY } from '@app/lib/constants';
import { App } from '@app/types/app';
import { useCallback, useEffect, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';

interface IUser {
  first_name: string;
  last_name: string;
  email: string;
  id: string;
}

const DashboardLayout = ({ user, apps = [] }: { user: IUser; apps: App[] }) => {
  const currentPath = useLocation();
  const navigate = useNavigate();
  const timeoutRef = useRef<number | null>(null);
  /*
  The Broadcast Channel API enables communication between different browser windows, tabs, iframes, and web workers. 
  creating a channel with name 'timeout' 
  */
  const bc = useRef<BroadcastChannel | null>(
    typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('timeout') : null
  );

  const resetTimer = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    // @ts-ignore
    timeoutRef.current = setTimeout(
      () => {
        navigate('/logout');
      },
      30 * 60 * 1000 // 30 minutes
    );
  }, []);

  useEffect(() => {
    // Initial timer setup
    resetTimer();

    const events = ['click', 'keypress'];

    const handleEvent = () => {
      resetTimer();
      if (bc.current) {
        bc.current.postMessage('resetTimer');
      }
    };

    if (bc.current) {
      try {
        // listening to the message from the channel
        bc.current.onmessage = (event) => {
          if (event.data === 'resetTimer') {
            resetTimer();
          }
        };
      } catch (error) {
        console.warn('BroadcastChannel not supported or failed to create:', error);
      }

      events.forEach((event) => {
        window.addEventListener(event, handleEvent);
      });
    } else {
      events.forEach((event) => {
        window.addEventListener(event, handleEvent);
      });
    }

    return () => {
      if (bc.current) {
        bc.current.close();
        bc.current = null;
      }

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      events.forEach((event) => {
        window.removeEventListener(event, handleEvent);
      });
    };
  }, [resetTimer]);

  useEffect(() => {
    localStorage.setItem(CURRENT_PATH_KEY, `${currentPath.pathname}${currentPath.search}`);
  }, [currentPath]);

  return (
    <div className="flex h-full w-full">
      <div className={'relative flex h-full flex-1 flex-col'}>
        <Topbar user={user} apps={apps} />
        <main className="flex-1 overflow-auto bg-[#f6fafd]">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
