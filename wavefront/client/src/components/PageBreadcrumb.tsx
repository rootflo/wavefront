import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { cn } from '@app/lib/utils';
import React from 'react';
import { useNavigate } from 'react-router';

export interface Crumb {
  label: React.ReactNode;
  /** Makes the crumb a link; leave it out for the page being viewed. */
  to?: string;
  /** Shows a placeholder while the page's name is still loading. */
  loading?: boolean;
}

/** The desktop breadcrumb at the top of an app page. "Apps" comes first; pass the crumbs after it. */
const PageBreadcrumb = ({ items, className }: { items: Crumb[]; className?: string }) => {
  const navigate = useNavigate();
  const crumbs: Crumb[] = [{ label: 'Apps', to: '/apps' }, ...items];

  return (
    <Breadcrumb className={cn('mb-4 hidden md:block', className)}>
      <BreadcrumbList>
        {crumbs.map((crumb, index) => (
          <React.Fragment key={index}>
            {index > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {crumb.to ? (
                <BreadcrumbLink asChild>
                  <button
                    type="button"
                    onClick={() => navigate(crumb.to!)}
                    className="hover:text-foreground cursor-pointer"
                  >
                    {crumb.label}
                  </button>
                </BreadcrumbLink>
              ) : (
                <BreadcrumbPage loading={crumb.loading}>{crumb.label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
};

export default PageBreadcrumb;
