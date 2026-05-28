import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { Outlet } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Tabs, TabsList, TabsTrigger } from '@app/components/ui/tabs';

const VoiceAgentsLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const location = useLocation();
  const navigate = useNavigate();

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
    <div className="flex h-full w-full flex-col bg-white">
      <div className="flex h-full w-full flex-col">
        {/* Breadcrumb */}
        <div className="px-8 pt-8">
          <Breadcrumb className="mb-4">
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
        <div className="border-gray-200 px-8">
          <div className="mb-6">
            <h1 className="animate-fade-in text-3xl font-bold text-gray-900">Voice Agents</h1>
            <p className="animate-fade-in mt-2 text-gray-600">
              Manage AI voice agents with LLM, TTS, STT, and telephony configurations
            </p>
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
        <div className="flex-1 overflow-auto px-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default VoiceAgentsLayout;
