import { Button } from '@wavefront/ui/button';
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from '@wavefront/ui/empty';
import { useAuthStore } from '@app/store';
import { useNavigate } from 'react-router';

const NotFoundPage = () => {
  const navigate = useNavigate();
  const { authenticated } = useAuthStore();

  const handleGoBack = () => {
    if (authenticated) {
      navigate('/apps');
    } else {
      navigate('/login');
    }
  };

  return (
    <Empty>
      <EmptyHeader>
        <EmptyTitle>404 - Not Found</EmptyTitle>
        <EmptyDescription>
          The page you&apos;re looking for doesn&apos;t exist. <br />
          <Button className="mt-4" variant="outline" size="sm" onClick={handleGoBack}>
            Go Back
          </Button>
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <EmptyDescription>
          Need help? <a href="#">Contact support</a>
        </EmptyDescription>
      </EmptyContent>
    </Empty>
  );
};
export default NotFoundPage;
