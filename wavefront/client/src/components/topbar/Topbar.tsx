import { RootfloIcon } from '@app/assets/icons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { IUser } from '@app/pages/types';
import { useAuthStore } from '@app/store';
import { useDashboardStore } from '@app/store/dashboard-store';
import { App } from '@app/types/app';
import { UserIcon } from 'lucide-react';
import { useEffect } from 'react';
import { useNavigate } from 'react-router';

const Topbar = ({ user, apps = [] }: { user: IUser; apps: App[] }) => {
  const { selectedApp, setSelectedApp } = useDashboardStore();
  const { authenticated } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    navigate('/logout');
  };

  const handleNavIconClick = () => {
    if (authenticated) {
      navigate('/apps');
    } else {
      navigate('/login');
    }
  };

  useEffect(() => {
    const pageUrl = new URL(window.location.href);
    const appId = pageUrl.pathname.split('/')[2];
    setSelectedApp(apps.find((app) => app.id === appId) || null);
  }, [apps]);

  return (
    <div className="flex h-20 justify-between border-b">
      <a className="flex min-w-[240px] cursor-pointer justify-center border-r px-8 py-5" onClick={handleNavIconClick}>
        <RootfloIcon />
      </a>

      <div className="flex w-full justify-between px-8 py-5">
        <div id="left_part" className="flex items-center justify-center gap-3">
          <p className="text-[16.33px] font-bold text-black">AI Middleware</p>
          {/* <p>|</p> */}
          {/* <div className="flex items-center justify-center gap-1">
            <p className="text-[13px] font-normal">Powered by </p>
            <RootfloIcon />
          </div> */}
        </div>
        <div id="right_part" className="flex items-center justify-center gap-3">
          {apps && (
            <Select
              value={selectedApp?.id}
              onValueChange={(value) => {
                const currentPath = location.pathname;
                // Extract the path after /apps/:appId/ and take only the first segment
                const pathMatch = currentPath.match(/\/apps\/[^/]+\/([^/]+)/);
                const subPath = pathMatch ? `${pathMatch[1]}` : 'agents';
                setSelectedApp(apps.find((app) => app.id === value) || null);
                navigate(`/apps/${value}/${subPath}`);
              }}
            >
              <SelectTrigger className="w-[240px] cursor-pointer">
                <SelectValue placeholder="Select an app" />
              </SelectTrigger>
              <SelectContent>
                {apps.map((app) => (
                  <SelectItem className="cursor-pointer" key={app.id} value={app.id}>
                    {app.app_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}{' '}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <div className="border-heading flex w-[180px] cursor-pointer items-center gap-1 rounded-full border p-1.5 capitalize">
                <UserIcon />
                <p className="text-heading w-full truncate text-[13px] font-medium">
                  {user.first_name} {user.last_name}
                </p>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="end">
              <DropdownMenuLabel>My Account</DropdownMenuLabel>
              <DropdownMenuItem className="cursor-pointer" onClick={handleLogout}>
                Log out
                <DropdownMenuShortcut>⇧⌘Q</DropdownMenuShortcut>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
};

export default Topbar;
