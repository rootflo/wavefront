import {
  AiAgentIcon,
  ApiIcon,
  DatasourcesIcon,
  ModelInferenceIcon,
  ModelRepositoryIcon,
  // PermissionIcon,
  PhoneIcon,
  RagIcon,
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
  // {
  //   name: 'Authenticators',
  //   icon: PermissionIcon,
  //   link: `/apps/:appId/authenticators`,
  //   description: 'Manage authentication provider configurations',
  // },
  {
    id: 'datasources',
    name: 'Datasources',
    icon: DatasourcesIcon,
    link: `/apps/:appId/datasources`,
    description: 'Manage and configure data sources for this application',
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
    id: 'model-inference',
    name: 'Model Inference',
    icon: ModelInferenceIcon,
    link: `/apps/:appId/model-inference`,
    description: 'Manage and configure model inference for this application',
    alpha: true,
  },
  {
    id: 'knowledge-bases',
    name: 'RAG Service',
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
  // {
  //   name: 'Pipelines',
  //   icon: WorkflowIcon,
  //   link: `/apps/:appId/data-pipelines`,
  //   description: 'Manage and configure DBT pipelines for this application',
  // },
];

let finalNavItems = navItems;
if (appEnv.isApiServicesEnabled) {
  const apiServiceNavItem = {
    id: 'api-services',
    name: 'API Services',
    icon: ApiIcon,
    link: `/apps/:appId/api-services`,
    description: 'Manage API Connectors',
  };
  finalNavItems = [navItems[0], apiServiceNavItem, ...navItems.slice(1)];
}

const AppLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="h-full bg-white">
      <div className="flex h-full w-full overflow-auto">
        <div className="flex h-full w-[240px] flex-col gap-3 border-r border-gray-200 p-5">
          {finalNavItems.map((item) => {
            const isActive = item.id === location.pathname.split('/')[3];
            return (
              <div
                key={item.id}
                className={clsx(
                  'cursor-pointer rounded-lg border-[0.5px] border-[#EFF0F1] p-3',
                  isActive && 'bg-[#FBFBFB]'
                )}
                onClick={() => navigate(item.link.replace(':appId', app!))}
              >
                <div className="flex items-center gap-2">
                  <item.icon color={isActive ? '#000' : '#fff'} />
                  <p
                    className={clsx(
                      isActive ? 'font-medium text-[#101010]' : 'font-normal text-[#585858]',
                      'flex items-center gap-2 text-sm'
                    )}
                  >
                    <span>{item.name}</span>
                    {item.alpha && <span className="mb-2 text-[10px] text-green-500">alpha</span>}
                  </p>
                </div>
                <div
                  className={clsx(
                    'overflow-hidden transition-all duration-300 ease-in-out',
                    isActive ? 'max-h-16 opacity-100' : 'max-h-0 opacity-0'
                  )}
                >
                  <p className="mt-2 text-xs text-[#9F9F9F]">{item.description}</p>
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex-1 overflow-auto">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default AppLayout;
