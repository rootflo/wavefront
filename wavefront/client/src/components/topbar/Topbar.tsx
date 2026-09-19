import { RootfloIcon } from '@app/assets/icons';
import ThemeToggle from '@app/components/ThemeToggle';
import SelectAppDialog from '@app/components/topbar/SelectAppDialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { formatAppName } from '@app/lib/utils';
import { IUser } from '@app/pages/types';
import { useAuthStore } from '@app/store';
import { useDashboardStore } from '@app/store/dashboard-store';
import { useThemeStore } from '@app/store/theme-store';
import { App } from '@app/types/app';
import { LogOut, Settings, UserIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

const Topbar = ({ user, apps = [] }: { user: IUser; apps: App[] }) => {
  const { selectedApp, setSelectedApp } = useDashboardStore();
  const { authenticated } = useAuthStore();
  const theme = useThemeStore((state) => state.theme);
  const navigate = useNavigate();
  const location = useLocation();
  const [appPickerOpen, setAppPickerOpen] = useState(false);

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

  const handleSelectApp = (app: App) => {
    const pathMatch = location.pathname.match(/\/apps\/[^/]+\/([^/]+)/);
    const subPath = pathMatch ? pathMatch[1] : 'agents';
    setSelectedApp(app);
    setAppPickerOpen(false);
    navigate(`/apps/${app.id}/${subPath}`);
  };

  useEffect(() => {
    const pageUrl = new URL(window.location.href);
    const appId = pageUrl.pathname.split('/')[2];
    setSelectedApp(apps.find((app) => app.id === appId) || null);
  }, [apps, setSelectedApp]);

  return (
    <header className="relative z-20 h-14 shrink-0 overflow-hidden">
      <div aria-hidden className="frost-wash pointer-events-none absolute inset-0">
        <div className="frost-blob-a absolute -top-16 left-0 h-40 w-56 rounded-full blur-3xl" />
        <div className="frost-blob-b absolute -top-10 left-1/3 h-36 w-52 rounded-full blur-3xl" />
        <div className="frost-blob-c absolute right-8 -bottom-16 h-40 w-56 rounded-full blur-3xl" />
        <div className="frost-nav-overlay absolute inset-0" />
      </div>

      <div className="frost-glass relative flex h-full items-stretch">
        <a
          className="flex w-[200px] shrink-0 cursor-pointer items-center justify-center px-4 transition-colors hover:bg-white/20 dark:hover:bg-white/5"
          onClick={handleNavIconClick}
        >
          <img
            src="/wavefront.png"
            alt="Wavefront"
            className={`object-contain ${theme === 'dark' ? 'brightness-0 invert' : ''}`}
            width={120}
          />
        </a>

        <div className="flex min-w-0 flex-1 items-center justify-between gap-4 pr-8 pl-5">
          <div className="flex min-w-0 items-center gap-6">
            <div className="flex shrink-0 items-center gap-1.5">
              <p className="frost-text-subtle text-[10px] font-semibold tracking-[0.14em] uppercase">Powered by</p>
              <RootfloIcon height={14} width={38} color={theme === 'dark' ? '#e2e8f0' : undefined} />
            </div>

            {apps.length > 0 ? (
              <>
                <button
                  type="button"
                  aria-label="Select app"
                  onClick={() => setAppPickerOpen(true)}
                  className="frost-text hover:bg-frost-glass flex h-8 max-w-[200px] cursor-pointer items-center gap-1.5 rounded-full border border-slate-300 bg-transparent px-3 transition-colors outline-none dark:border-slate-500"
                >
                  <span className="min-w-0 flex-1 truncate text-left text-[13px] font-medium lowercase">
                    {selectedApp ? formatAppName(selectedApp.app_name) : 'Select an app'}
                  </span>
                </button>

                <SelectAppDialog
                  open={appPickerOpen}
                  onOpenChange={setAppPickerOpen}
                  apps={apps}
                  selectedAppId={selectedApp?.id}
                  onSelect={handleSelectApp}
                />
              </>
            ) : null}
          </div>

          <div className="flex items-center gap-6">
            <ThemeToggle />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="frost-glass-strong frost-text border-frost-border ring-frost-border flex h-8 w-[160px] cursor-pointer items-center gap-1.5 rounded-md border px-2 ring-1 transition-colors hover:opacity-90"
                >
                  <UserIcon className="frost-text-muted h-3.5 w-3.5 shrink-0" />
                  <span className="truncate text-[13px] font-medium capitalize">
                    {user.first_name} {user.last_name}
                  </span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="frost-dialog border-frost-border ring-frost-border w-[160px] min-w-0 p-1.5 ring-1"
                align="end"
                sideOffset={8}
              >
                <DropdownMenuLabel className="px-2.5 py-2 font-normal">
                  <p className="frost-text text-[13px] leading-tight font-medium capitalize">
                    {user.first_name} {user.last_name}
                  </p>
                  {user.email ? (
                    <p className="frost-text-muted mt-0.5 truncate text-[11px] leading-tight font-normal normal-case">
                      {user.email}
                    </p>
                  ) : null}
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-frost-border" />
                <DropdownMenuItem
                  className="frost-text focus:bg-frost-glass focus:text-frost-text cursor-pointer gap-2 rounded-md px-2.5 py-2 text-[12px] [&>svg]:size-3"
                  onClick={() => navigate('/apps/users')}
                >
                  <Settings className="frost-text-muted size-4" />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="cursor-pointer gap-2 rounded-md px-2.5 py-2 text-[12px] text-red-600 focus:bg-red-500/10 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400 [&>svg]:size-3"
                  onClick={handleLogout}
                >
                  <LogOut className="size-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Topbar;
