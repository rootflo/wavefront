import { PageActionsContext } from '@app/components/PageActionsContext';
import React, { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { Outlet } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import PageTitle from '@app/components/PageTitle';
import { Tabs, TabsList, TabsTrigger } from '@app/components/ui/tabs';

const VoiceAgentsLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  // Where the page's search, filters and buttons render, so they sit on the title's row.
  const [actionsSlot, setActionsSlot] = useState<HTMLElement | null>(null);

  // Determine active tab based on current location
  const basePath = `/apps/${app}/voice-agents`;

  const getActiveTab = () => {
    if (location.pathname.startsWith(`${basePath}/stt-configs`)) {
      return 'stt-configs';
    }
    if (location.pathname.startsWith(`${basePath}/tts-configs`)) {
      return 'tts-configs';
    }
    if (location.pathname.startsWith(`${basePath}/telephony-configs`)) {
      return 'telephony-configs';
    }
    if (location.pathname.startsWith(`${basePath}/tools`)) {
      return 'tools';
    }
    return 'agents';
  };

  const activeTab = getActiveTab();

  const handleTabChange = (value: string) => {
    if (value === 'agents') {
      navigate(basePath);
    } else {
      navigate(`${basePath}/${value}`);
    }
  };

  return (
    <PageActionsContext.Provider value={{ element: actionsSlot }}>
      <div className="flex h-full min-h-0 w-full flex-col bg-transparent">
        <div className="flex min-h-0 flex-1 flex-col">
          {/* Breadcrumb */}
          <div className="px-4 pt-4 max-md:hidden sm:px-8 sm:pt-8">
            <Breadcrumb className="mb-4 hidden md:block">
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <button
                      type="button"
                      onClick={() => navigate('/apps')}
                      className="hover:text-foreground cursor-pointer"
                    >
                      Apps
                    </button>
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <button
                      type="button"
                      onClick={() => navigate(`/apps/${app}/voice-agents`)}
                      className="hover:text-foreground cursor-pointer"
                    >
                      Voice Agents
                    </button>
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          {/* Header */}
          <div className="border-frost-border px-4 max-md:pt-4 sm:px-8">
            <div className="mb-6 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between xl:gap-5">
              <div className="min-w-0">
                <PageTitle className="animate-fade-in">Voice Agents</PageTitle>
                <p className="animate-fade-in frost-text-muted mt-1 text-[13.5px] md:mt-2 md:text-sm">
                  Manage AI voice agents with LLM, TTS, STT, and telephony configurations
                </p>
              </div>
              <div ref={setActionsSlot} className="min-w-0 xl:shrink-0" />
            </div>

            {/* Navigation Tabs */}
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList>
                <TabsTrigger value="agents">Agents</TabsTrigger>
                <TabsTrigger value="tools">Tools</TabsTrigger>
                <TabsTrigger value="stt-configs">STT Configs</TabsTrigger>
                <TabsTrigger value="tts-configs">TTS Configs</TabsTrigger>
                <TabsTrigger value="telephony-configs">Telephony Configs</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Child Route Content */}
          <div className="min-h-0 flex-1 overflow-hidden px-4 pt-4 pb-4 max-md:overflow-y-auto sm:px-8 sm:pt-6 sm:pb-8">
            <Outlet />
          </div>
        </div>
      </div>
    </PageActionsContext.Provider>
  );
};

export default VoiceAgentsLayout;
