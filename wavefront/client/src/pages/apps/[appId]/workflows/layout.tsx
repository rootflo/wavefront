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

const WorkflowsLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Determine active tab based on current location
  const basePath = `/apps/${app}/workflows`;

  const getActiveTab = () => {
    if (location.pathname.startsWith(`${basePath}/pipelines`)) {
      return 'pipelines';
    }
    return 'workflows';
  };

  const activeTab = getActiveTab();

  const handleTabChange = (value: string) => {
    if (value === 'workflows') {
      navigate(basePath);
    } else {
      navigate(`${basePath}/pipelines`);
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
                    onClick={() => navigate(`/apps/${app}/workflows`)}
                    className="hover:text-foreground cursor-pointer"
                  >
                    Workflows
                  </button>
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>

        {/* Header */}
        <div className="border-gray-200 px-8">
          <div className="mb-6">
            <h1 className="animate-fade-in text-3xl font-bold text-gray-900">Workflows</h1>
            <p className="animate-fade-in mt-2 text-gray-600">Manage AI workflows and pipelines for your application</p>
          </div>

          {/* Navigation Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
            <TabsList>
              <TabsTrigger value="workflows">Workflows</TabsTrigger>
              <TabsTrigger value="pipelines">Pipelines</TabsTrigger>
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

export default WorkflowsLayout;
