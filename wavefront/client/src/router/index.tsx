import DashboardLayout from '@app/components/DashboardLayout';
import ProtectedLayout from '@app/components/ProtectedLayout';
import { useGetAllApps, useGetCurrentUser } from '@app/hooks';
import NotFoundPage from '@app/not-found';
import { useAuthStore } from '@app/store';
import { ReactNode } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import routes from './routes';

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

  return (
    <BrowserRouter>
      <Routes>
        {routes.public.map((route) => (
          <Route key={route.path} path={route.path} element={route.element} />
        ))}

        <Route element={<ProtectedLayout setAuthenticatedState={setAuthenticatedState} />}>
          <Route
            element={
              <DashboardLayout user={user || { first_name: '', last_name: '', email: '', id: '' }} apps={apps} />
            }
          >
            {routes.private.map((route) => renderChildren(route))}
            {routes.admin.map((route) => renderChildren(route))}
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
