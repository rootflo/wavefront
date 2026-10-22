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
import { isLiveStatus } from '@app/lib/app-status';
import { formatAppName } from '@app/lib/utils';
import { IUser } from '@app/pages/types';
import { useAuthStore } from '@app/store';
import { useDashboardStore } from '@app/store/dashboard-store';
import { useThemeStore } from '@app/store/theme-store';
import { App } from '@app/types/app';
import { ChevronRight, ChevronsUpDown, LogOut, Menu, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

const Topbar = ({ user, apps = [] }: { user: IUser; apps: App[] }) => {
  const { selectedApp, setSelectedApp, setMobileNavOpen } = useDashboardStore();
  const { authenticated } = useAuthStore();
  const theme = useThemeStore((state) => state.theme);
  const navigate = useNavigate();
  const location = useLocation();
  const [appPickerOpen, setAppPickerOpen] = useState(false);

  // The workspace menu only exists inside an app's pages (/apps/:appId/<section>).
  const pathParts = location.pathname.split('/');
  const hasWorkspaceMenu = pathParts[1] === 'apps' && Boolean(pathParts[3]) && pathParts[2] !== 'edit';

  // The section of the app being viewed, e.g. "Agents", shown after the app switcher.
  const sectionName = pathParts[3]
    ? pathParts[3]
        .split('-')
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ')
    : '';

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
    <header className="relative z-20 h-14 shrink-0">
      <div className="frost-glass border-frost-border relative flex h-full items-center border-b">
        {hasWorkspaceMenu ? (
          <button
            type="button"
            aria-label="Open navigation menu"
            onClick={() => setMobileNavOpen(true)}
            className="frost-text hover:bg-frost-glass flex w-11 shrink-0 cursor-pointer items-center justify-center md:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
        ) : null}
        <a className="flex shrink-0 cursor-pointer items-center px-3 sm:px-4 md:w-[208px]" onClick={handleNavIconClick}>
          <span className="relative inline-flex shrink-0 items-end gap-1.5">
            <img
              src="/wavefront.png"
              alt="Wavefront"
              className={`object-contain ${theme === 'dark' ? 'brightness-0 invert' : ''}`}
              width={110}
            />
            <span className="frost-text-subtle absolute -right-12 -bottom-2 mb-px hidden items-center gap-1 text-[8.5px] tracking-[0.1em] lg:flex">
              by
              <RootfloIcon height={11} width={30} color={theme === 'dark' ? '#e2e8f0' : undefined} />
            </span>
          </span>
        </a>

        <div className="flex min-w-0 flex-1 items-center justify-between gap-2 pr-3 pl-2 sm:gap-4 sm:pr-8 sm:pl-5">
          <div className="flex min-w-0 items-center gap-3 sm:gap-6">
            {apps.length > 0 ? (
              <>
                <button
                  type="button"
                  aria-label="Select app"
                  onClick={() => setAppPickerOpen(true)}
                  className="frost-glass-strong frost-text border-frost-border flex h-[38px] max-w-[160px] cursor-pointer items-center gap-2 rounded-xl border pr-1.5 pl-1.5 transition-colors outline-none hover:opacity-90 sm:max-w-[240px] sm:pr-2.5"
                >
                  <span className="flex size-[26px] shrink-0 items-center justify-center rounded-lg bg-[linear-gradient(135deg,#2f6df6,#8b5cf6)] text-xs font-extrabold text-white uppercase">
                    {selectedApp ? formatAppName(selectedApp.app_name).charAt(0) : '?'}
                  </span>
                  <span className="hidden min-w-0 flex-1 truncate text-left text-[13.5px] font-semibold sm:block">
                    {selectedApp ? formatAppName(selectedApp.app_name) : 'Select an app'}
                  </span>
                  {selectedApp?.status && isLiveStatus(selectedApp.status) ? (
                    <span className="hidden size-[7px] shrink-0 rounded-full bg-emerald-500 sm:block" aria-hidden />
                  ) : null}
                  <ChevronsUpDown className="frost-text-muted size-3.5 shrink-0" />
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
            {sectionName ? (
              <span className="frost-text-muted hidden items-center gap-1.5 text-[13px] md:flex">
                <ChevronRight className="size-3.5" />
                <b className="frost-text font-semibold">{sectionName}</b>
              </span>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-3 sm:gap-6">
            <ThemeToggle />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="Account menu"
                  className="flex size-9 cursor-pointer items-center justify-center rounded-full bg-[linear-gradient(135deg,#8b5cf6,#2f6df6)] text-[13px] font-bold text-white uppercase ring-2 ring-[var(--frost-border)] transition-opacity outline-none hover:opacity-90"
                >
                  {(user.first_name?.[0] ?? '') + (user.last_name?.[0] ?? '') || '?'}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="frost-dialog border-frost-border ring-frost-border w-[200px] min-w-0 rounded-xl p-1.5 ring-1"
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
