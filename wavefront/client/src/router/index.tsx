import DashboardLayout from '@app/components/DashboardLayout';
import ProtectedLayout from '@app/components/ProtectedLayout';
import { useGetAllApps, useGetCurrentUser } from '@app/hooks';
import NotFoundPage from '@app/not-found';
import { useAuthStore } from '@app/store';
import { ReactNode } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import routes from './routes';
import { ExtensionBoundary, useExtensionRoutes, useLoadExtensions } from '@app/extensions';

const APP_ROUTE_PATH = 'apps/:app';

const extensionFallback = <div className="frost-text-muted p-6 text-sm">This page could not be loaded.</div>;

interface ChildrenRoute {
  index?: boolean;
  element: ReactNode;
  path?: string;
  children?: ChildrenRoute[];
}
interface Routes {
  path: string;
  element: ReactNode;
  children?: ChildrenRoute[];
}
const renderChildren = (route: Routes, parentKey = '') => {
  const routeKey = parentKey ? `${parentKey}-${route.path}` : route.path;

  if (route.children) {
    return (
      <Route key={routeKey} path={route.path} element={route.element}>
        {route.children.map((child, index) => {
          const childKey = child.path || (child.index ? 'index' : `child-${index}`);
          if (child.children) {
            return renderChildren(
              {
                path: child.path || '',
                element: child.element,
                children: child.children,
              },
              routeKey
            );
          }
          return (
            <Route
              key={`${routeKey}-${childKey}`}
              index={child.index}
              path={child.index ? undefined : child.path}
              element={child.element}
            />
          );
        })}
      </Route>
    );
  }
  return <Route key={routeKey} path={route.path} element={route.element} />;
};

const AppRouter = () => {
  const { authenticated, setAuthenticatedState } = useAuthStore();

  const { data: user } = useGetCurrentUser(authenticated);
  const { data: apps = [] } = useGetAllApps(authenticated);

  // Pages contributed by remotes: app pages join the app layout's children,
  // console pages sit beside the other console pages.
  useLoadExtensions(authenticated);
  const extensionAppRoutes = useExtensionRoutes('app');
  const extensionConsoleRoutes = useExtensionRoutes('console');
  const isolate = (source: string, element: ReactNode) => (
    <ExtensionBoundary source={source} fallback={extensionFallback}>
      {element}
    </ExtensionBoundary>
  );
  const privateRoutes: Routes[] = [
    ...routes.private.map((route) =>
      route.path === APP_ROUTE_PATH
        ? {
            ...route,
            children: [
              ...(route.children ?? []),
              ...extensionAppRoutes.map(({ source, value }) => ({
                path: value.path,
                element: isolate(source, value.element),
              })),
            ],
          }
        : route
    ),
    ...extensionConsoleRoutes.map(({ source, value }) => ({
      path: `/${value.path}`,
      element: isolate(source, value.element),
    })),
  ];

  return (
    <BrowserRouter>
      <Routes>
        {routes.public.map((route) => (
          <Route key={route.path} path={route.path} element={route.element} />
        ))}

        <Route element={<ProtectedLayout setAuthenticatedState={setAuthenticatedState} />}>
          <Route
            element={
              <DashboardLayout
                user={user || { first_name: '', last_name: '', email: '', id: '', role: '' }}
                apps={apps}
              />
            }
          >
            {privateRoutes.map((route) => renderChildren(route))}
            {routes.admin.map((route) => renderChildren(route))}
          </Route>
          {routes.fullscreen.map((route) => renderChildren(route))}
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
