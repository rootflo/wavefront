import { PageActionsContext } from '@app/components/PageActionsContext';
import PageTitle from '@app/components/PageTitle';
import React, { useState } from 'react';
import { useLocation, useParams } from 'react-router';
import clsx from 'clsx';
import { Outlet } from 'react-router';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const WorkflowsLayout: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  // Where the page's search, filters and buttons render, so they sit on the title's row.
  const [actionsSlot, setActionsSlot] = useState<HTMLElement | null>(null);
  const location = useLocation();
  // On a phone the list keeps its heading, but a workflow's own page gives the space to its chat.
  const isListPage = location.pathname.replace(/\/$/, '').endsWith('/workflows');

  return (
    <PageActionsContext.Provider value={{ element: actionsSlot }}>
      <div className="flex h-full min-h-0 w-full flex-col bg-transparent">
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="px-4 pt-4 max-md:hidden sm:px-8 sm:pt-8">
            <PageBreadcrumb items={[{ label: 'Workflows', to: `/apps/${app}/workflows` }]} />
          </div>

          {/* Header */}
          <div className={clsx('border-frost-border px-4 sm:px-8', isListPage ? 'max-md:pt-4' : 'hidden')}>
            <div className="mb-5 flex flex-col gap-3 md:mb-8 xl:flex-row xl:items-end xl:justify-between xl:gap-5">
              <div className="min-w-0">
                <PageTitle className="animate-fade-in">Workflows</PageTitle>
                <p className="animate-fade-in frost-text-muted mt-1 text-[13.5px] md:mt-2 md:text-sm">
                  Manage AI workflows for your application
                </p>
              </div>
              <div ref={setActionsSlot} className="min-w-0 xl:shrink-0" />
            </div>
          </div>

          {/* Child Route Content */}
          <div
            className={clsx(
              'min-h-0 flex-1 overflow-y-auto px-4 pb-4 sm:px-8 sm:pb-8',
              !isListPage && 'pt-1 max-md:pt-3'
            )}
          >
            <Outlet />
          </div>
        </div>
      </div>
    </PageActionsContext.Provider>
  );
};

export default WorkflowsLayout;
