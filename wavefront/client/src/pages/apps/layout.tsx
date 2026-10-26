import AppsBackdrop from '@app/components/AppsBackdrop';
import { appEnv } from '@app/config/env';
import clsx from 'clsx';
import {
  AudioLines,
  BookOpen,
  Bot,
  Braces,
  BrainCircuit,
  CalendarClock,
  ChevronDown,
  Database,
  KeyRound,
  Mail,
  MessageSquareText,
  Plug,
  ShieldCheck,
  SlidersHorizontal,
  Webhook,
  Workflow,
} from 'lucide-react';
import { useDashboardStore } from '@app/store/dashboard-store';
import React, { useEffect, useRef, useState } from 'react';
import { saveLastApp } from '@app/lib/last-app';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router';

interface NavItem {
  id: string;
  name: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  link: string;
  description: string;
  alpha?: boolean;
}

const navItems: NavItem[] = [
  {
    id: 'agents',
    name: 'Agents',
    icon: Bot,
    link: `/apps/:appId/agents`,
    description: 'Manage and configure agents for this application',
  },
  {
    id: 'authenticators',
    name: 'Authenticators',
    icon: KeyRound,
    link: `/apps/:appId/authenticators`,
    description: 'Manage authentication provider configurations',
  },
  {
    id: 'chatbots',
    name: 'Chatbots',
    icon: MessageSquareText,
    link: `/apps/:appId/chatbots`,
    description: 'Configure chatbots with a system prompt and model',
  },
  {
    id: 'configurations',
    name: 'Configurations',
    icon: SlidersHorizontal,
    link: `/apps/:appId/configurations`,
    description: 'Static reference data workflows read at runtime',
  },
  {
    id: 'datasources',
    name: 'Datasources',
    icon: Database,
    link: `/apps/:appId/datasources`,
    description: 'Manage and configure data sources for this application',
  },
  {
    id: 'email-connections',
    name: 'Emails',
    icon: Mail,
    link: `/apps/:appId/email-connections`,
    description: 'Connect mailboxes agents, triggers and jobs send and read through',
  },
  {
    id: 'oauth-apps',
    name: 'OAuth Apps',
    icon: Plug,
    link: `/apps/:appId/oauth-apps`,
    description: 'Register OAuth apps mailboxes connect through',
  },
  {
    id: 'scheduled-jobs',
    name: 'Scheduled Jobs',
    icon: CalendarClock,
    link: `/apps/:appId/scheduled-jobs`,
    description: 'Schedule dynamic query reports to be emailed automatically',
  },
  {
    id: 'functions',
    name: 'Functions',
    icon: Braces,
    link: `/apps/:appId/functions`,
    description: 'Create, manage, and execute functions',
  },
  {
    id: 'model-hub',
    name: 'Model Hub',
    icon: BrainCircuit,
    link: `/apps/:appId/model-hub`,
    description: 'Manage and configure LLMs for your application',
  },
  {
    id: 'guardrails',
    name: 'Guardrails',
    icon: ShieldCheck,
    link: `/apps/:appId/guardrails`,
    description: 'Configure AI safety policies for your application',
  },
  {
    id: 'knowledge-bases',
    name: 'Knowledge Bases',
    icon: BookOpen,
    link: `/apps/:appId/knowledge-bases`,
    description: 'Manage and configure knowledge bases for this application',
  },
  {
    id: 'voice-agents',
    name: 'Voice Agents',
    icon: AudioLines,
    link: `/apps/:appId/voice-agents`,
    description: 'Manage AI voice agents with LLM, TTS, STT, and telephony',
  },
  {
    id: 'workflows',
    name: 'Workflows',
    icon: Workflow,
    link: `/apps/:appId/workflows`,
    description: 'Manage and configure workflows for this application',
  },
];

const finalNavItems = [...navItems];
if (appEnv.isApiServicesEnabled) {
  finalNavItems.push({
    id: 'api-services',
    name: 'API Services',
    icon: Webhook,
    link: `/apps/:appId/api-services`,
    description: 'Manage API Connectors',
  });
}
finalNavItems.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

// The same pages as before, grouped by what you do with them. Anything not listed lands in "More".
const NAV_GROUPS: { title: string; ids: string[] }[] = [
  { title: 'Build', ids: ['agents', 'workflows', 'voice-agents', 'chatbots', 'functions'] },
  { title: 'Data', ids: ['datasources', 'knowledge-bases', 'configurations', 'api-services'] },
  { title: 'Connect', ids: ['model-hub', 'email-connections', 'oauth-apps', 'authenticators'] },
  { title: 'AI Governance', ids: ['guardrails'] },
  { title: 'Others', ids: ['scheduled-jobs'] },
];
// Sizes of the sidebar pieces in px, used to work out how many groups fit without measuring the DOM.
const NAV_ITEM_HEIGHT = 34;
const NAV_ITEM_GAP = 2;
const NAV_GROUP_GAP = 16;
const NAV_GROUP_TITLE_HEIGHT = 20;
const NAV_PADDING = 24;

const expandedGroupHeight = (itemCount: number) =>
  NAV_GROUP_TITLE_HEIGHT + itemCount * NAV_ITEM_HEIGHT + Math.max(itemCount - 1, 0) * NAV_ITEM_GAP;

const groupedNav = (() => {
  const groups = NAV_GROUPS.map((group) => ({
    title: group.title,
    items: group.ids
      .map((id) => finalNavItems.find((item) => item.id === id))
      .filter((item): item is NavItem => !!item),
  }));
  const placed = new Set(NAV_GROUPS.flatMap((group) => group.ids));
  const rest = finalNavItems.filter((item) => !placed.has(item.id));
  if (rest.length > 0) groups.push({ title: 'More', items: rest });
  return groups.filter((group) => group.items.length > 0);
})();

const AppLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  // Whichever app the user is inside becomes the "jump back in" app on the apps home page.
  useEffect(() => {
    if (app) saveLastApp(app);
  }, [app]);
  // When the sidebar is too short for every group, the ones at the bottom collapse to just their title.
  const navRef = useRef<HTMLElement>(null);
  const [navHeight, setNavHeight] = useState(0);
  const [manualOpen, setManualOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const observer = new ResizeObserver(() => setNavHeight(nav.clientHeight));
    observer.observe(nav);
    setNavHeight(nav.clientHeight);
    return () => observer.disconnect();
  }, []);

  const activeSection = location.pathname.split('/')[3];
  const autoOpen = (() => {
    const open: Record<string, boolean> = {};
    // Until the height is known, show everything.
    if (navHeight === 0) return Object.fromEntries(groupedNav.map((group) => [group.title, true]));
    let used = NAV_PADDING;
    let collapsing = false;
    groupedNav.forEach((group, index) => {
      const gap = index > 0 ? NAV_GROUP_GAP : 0;
      const containsActive = group.items.some((item) => item.id === activeSection);
      const remainingTitles = groupedNav.length - index - 1;
      // Reserve room for the titles of the groups after this one, so they stay reachable.
      const reserve = remainingTitles * (NAV_GROUP_GAP + NAV_GROUP_TITLE_HEIGHT);
      const fits = used + gap + expandedGroupHeight(group.items.length) + reserve <= navHeight;
      // Strictly from the bottom: once one group collapses, every group after it does too.
      open[group.title] = (fits && !collapsing) || containsActive;
      if (!open[group.title]) collapsing = true;
      used += gap + (open[group.title] ? expandedGroupHeight(group.items.length) : NAV_GROUP_TITLE_HEIGHT);
    });
    return open;
  })();
  const isGroupOpen = (title: string) => manualOpen[title] ?? autoOpen[title];

  const mobileNavOpen = useDashboardStore((state) => state.mobileNavOpen);
  const setMobileNavOpen = useDashboardStore((state) => state.setMobileNavOpen);
  return (
    <div className="relative isolate h-full overflow-hidden">
      <AppsBackdrop />

      <div className="relative flex h-full min-h-0 w-full">
        {mobileNavOpen ? (
          <div
            aria-hidden
            className="fixed inset-0 z-30 bg-slate-900/40 md:hidden"
            onClick={() => setMobileNavOpen(false)}
          />
        ) : null}

        <aside
          className={clsx(
            'frost-glass flex h-full min-h-0 w-[200px] shrink-0 flex-col',
            'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-[240px] max-md:pt-14 max-md:transition-transform max-md:duration-200',
            'max-md:bg-frost-dialog! max-md:border-frost-border max-md:border-r max-md:shadow-xl max-md:[backdrop-filter:none]!',
            mobileNavOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full'
          )}
        >
          <nav ref={navRef} className="no-scrollbar flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2.5 py-3">
            {groupedNav.map((group) => (
              <div key={group.title} className="flex flex-col gap-0.5">
                <button
                  type="button"
                  aria-expanded={isGroupOpen(group.title)}
                  onClick={() => setManualOpen((current) => ({ ...current, [group.title]: !isGroupOpen(group.title) }))}
                  className="frost-text-subtle hover:text-frost-text flex h-5 cursor-pointer items-center justify-between px-2.5 text-[10.5px] font-bold tracking-[0.1em] uppercase transition-colors"
                >
                  {group.title}
                  <ChevronDown
                    className={clsx(
                      'size-3 transition-transform duration-200',
                      !isGroupOpen(group.title) && '-rotate-90'
                    )}
                  />
                </button>
                {(isGroupOpen(group.title) ? group.items : []).map((item) => {
                  const isActive = item.id === location.pathname.split('/')[3];
                  return (
                    <button
                      key={item.id}
                      type="button"
                      title={item.description}
                      onClick={() => {
                        navigate(item.link.replace(':appId', app!));
                        setMobileNavOpen(false);
                      }}
                      className={clsx(
                        'group relative flex h-[34px] w-full cursor-pointer items-center gap-2.5 rounded-[10px] px-2.5 text-left transition-colors duration-200',
                        isActive
                          ? 'frost-text bg-[linear-gradient(90deg,rgb(47_109_246/0.16),transparent)]'
                          : 'frost-text-muted hover:text-frost-text hover:bg-black/5 dark:hover:bg-white/6'
                      )}
                    >
                      {isActive ? (
                        <span className="absolute top-[7px] bottom-[7px] -left-2.5 w-[3px] rounded-r-[3px] bg-[linear-gradient(#2f6df6,#8b5cf6)]" />
                      ) : null}
                      <item.icon
                        className="shrink-0"
                        color={isActive ? '#2f6df6' : 'var(--frost-text-muted)'}
                        width={16}
                        height={16}
                      />
                      <span
                        className={clsx(
                          'min-w-0 flex-1 truncate text-[13.5px] leading-none',
                          isActive ? 'font-medium' : 'font-normal'
                        )}
                      >
                        {item.name}
                      </span>
                      {item.alpha ? (
                        <span className="shrink-0 rounded bg-emerald-400/15 px-1 py-0.5 text-[9px] font-medium tracking-wide text-emerald-600 uppercase dark:text-emerald-400">
                          alpha
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
        </aside>

        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto bg-transparent">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
};

export default AppLayout;
