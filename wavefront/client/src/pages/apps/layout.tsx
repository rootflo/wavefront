import {
  AiAgentIcon,
  ApiIcon,
  ChatIcon,
  DatasourcesIcon,
  EmailIcon,
  ModelInferenceIcon,
  ModelRepositoryIcon,
  PermissionIcon,
  PhoneIcon,
  RagIcon,
  ScheduledJobsIcon,
  TriggerIcon,
  WorkflowIcon,
} from '@app/assets/icons';
import { appEnv } from '@app/config/env';
import clsx from 'clsx';
import React from 'react';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router';

const navItems = [
  {
    id: 'agents',
    name: 'Agents',
    icon: AiAgentIcon,
    link: `/apps/:appId/agents`,
    description: 'Manage and configure agents for this application',
  },
  {
    id: 'authenticators',
    name: 'Authenticators',
    icon: PermissionIcon,
    link: `/apps/:appId/authenticators`,
    description: 'Manage authentication provider configurations',
  },
  {
    id: 'chatbots',
    name: 'Chatbots',
    icon: ChatIcon,
    link: `/apps/:appId/chatbots`,
    description: 'Configure chatbots with a system prompt and model',
  },
  {
    id: 'configurations',
    name: 'Configurations',
    icon: ModelRepositoryIcon,
    link: `/apps/:appId/configurations`,
    description: 'Static reference data workflows read at runtime',
  },
  {
    id: 'datasources',
    name: 'Datasources',
    icon: DatasourcesIcon,
    link: `/apps/:appId/datasources`,
    description: 'Manage and configure data sources for this application',
  },
  {
    id: 'email-connections',
    name: 'Emails',
    icon: EmailIcon,
    link: `/apps/:appId/email-connections`,
    description: 'Connect mailboxes agents, triggers and jobs send and read through',
  },
  {
    id: 'oauth-apps',
    name: 'OAuth Apps',
    icon: PermissionIcon,
    link: `/apps/:appId/oauth-apps`,
    description: 'Register OAuth apps mailboxes connect through',
  },
  {
    id: 'triggers',
    name: 'Triggers',
    icon: TriggerIcon,
    link: `/apps/:appId/triggers`,
    description: 'Watch mailboxes and run agents or workflows on inbound email',
  },
  {
    id: 'scheduled-jobs',
    name: 'Scheduled Jobs',
    icon: ScheduledJobsIcon,
    link: `/apps/:appId/scheduled-jobs`,
    description: 'Schedule dynamic query reports to be emailed automatically',
  },
  {
    id: 'functions',
    name: 'Functions',
    icon: WorkflowIcon,
    link: `/apps/:appId/functions`,
    description: 'Create, manage, and execute functions',
  },
  {
    id: 'llm-repository',
    name: 'LLM Repository',
    icon: ModelRepositoryIcon,
    link: `/apps/:appId/llm-repository`,
    description: 'Manage and configure LLMs for your application',
  },
  {
    id: 'guardrails',
    name: 'Guardrails',
    icon: PermissionIcon,
    link: `/apps/:appId/guardrails`,
    description: 'Configure AI safety policies for your application',
  },
  {
    id: 'model-inference',
    name: 'Model Inference',
    icon: ModelInferenceIcon,
    link: `/apps/:appId/model-inference`,
    description: 'Manage and configure model inference for this application',
    alpha: true,
  },
  {
    id: 'knowledge-bases',
    name: 'Knowledge Bases',
    icon: RagIcon,
    link: `/apps/:appId/knowledge-bases`,
    description: 'Manage and configure knowledge bases for this application',
  },
  {
    id: 'voice-agents',
    name: 'Voice Agents',
    icon: PhoneIcon,
    link: `/apps/:appId/voice-agents`,
    description: 'Manage AI voice agents with LLM, TTS, STT, and telephony',
  },
  {
    id: 'workflows',
    name: 'Workflows',
    icon: WorkflowIcon,
    link: `/apps/:appId/workflows`,
    description: 'Manage and configure workflows for this application',
  },
];

const finalNavItems = [...navItems];
if (appEnv.isApiServicesEnabled) {
  finalNavItems.push({
    id: 'api-services',
    name: 'API Services',
    icon: ApiIcon,
    link: `/apps/:appId/api-services`,
    description: 'Manage API Connectors',
  });
}
finalNavItems.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

const AppLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="relative h-full overflow-hidden">
      <div aria-hidden className="frost-wash pointer-events-none absolute inset-y-0 left-0 w-[280px]">
        <div className="frost-blob-a absolute -top-10 -left-8 h-56 w-56 rounded-full blur-3xl" />
        <div className="frost-blob-b absolute top-1/3 -left-6 h-48 w-48 rounded-full blur-3xl" />
        <div className="frost-blob-c absolute bottom-8 left-4 h-52 w-52 rounded-full blur-3xl" />
        <div className="frost-wash-overlay absolute inset-0" />
      </div>

      <div className="relative flex h-full min-h-0 w-full">
        <aside className="frost-glass flex h-full min-h-0 w-[200px] shrink-0 flex-col">
          <div className="px-3 pt-3 pb-2">
            <p className="frost-text-subtle px-2 text-[10px] font-semibold tracking-[0.14em] uppercase">Workspace</p>
          </div>

          <nav className="no-scrollbar flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-3">
            {finalNavItems.map((item) => {
              const isActive = item.id === location.pathname.split('/')[3];
              return (
                <button
                  key={item.id}
                  type="button"
                  title={item.description}
                  onClick={() => navigate(item.link.replace(':appId', app!))}
                  className={clsx(
                    'group relative flex h-8 w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left transition-all duration-200',
                    isActive
                      ? 'frost-glass-strong frost-text ring-frost-border shadow-[var(--frost-inset-shadow)] ring-1'
                      : 'frost-text-muted hover:text-frost-text hover:bg-white/35 dark:hover:bg-white/5'
                  )}
                >
                  {isActive ? (
                    <span className="bg-brand absolute top-1/2 left-0 h-4 w-[2px] -translate-y-1/2 rounded-full" />
                  ) : null}
                  <item.icon
                    className="shrink-0"
                    color={isActive ? 'var(--frost-text)' : 'var(--frost-text-muted)'}
                    width={14}
                    height={14}
                  />
                  <span
                    className={clsx(
                      'min-w-0 flex-1 truncate text-[13px] leading-none',
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
          </nav>
        </aside>

        <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
          <div className="frost-content ring-frost-border h-full min-h-0 overflow-y-auto rounded-tl-[1.75rem] shadow-[-12px_4px_32px_-16px_rgba(15,23,42,0.18)] ring-1 ring-inset dark:shadow-[-12px_4px_32px_-16px_rgba(0,0,0,0.45)]">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
};

export default AppLayout;
