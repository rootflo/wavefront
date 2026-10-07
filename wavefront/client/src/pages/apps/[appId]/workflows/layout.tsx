import React from 'react';
import { useNavigate, useParams } from 'react-router';
import { Outlet } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';

const WorkflowsLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-transparent">
      <div className="flex min-h-0 flex-1 flex-col">
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
        <div className="border-frost-border px-8">
          <div className="mb-6">
            <h1 className="animate-fade-in frost-text text-3xl font-bold">Workflows</h1>
            <p className="animate-fade-in frost-text-muted mt-2">Manage AI workflows for your application</p>
          </div>
        </div>

        {/* Child Route Content */}
        <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default WorkflowsLayout;
