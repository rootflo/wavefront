import { Button } from '@app/components/ui/button';
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from '@app/components/ui/empty';

interface EmptyProps {
  title: string;
  description: string;
  actionText: string;
  onActionClick: () => void;
}

export function EmptyStateCard({ title, description, actionText, onActionClick }: EmptyProps) {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" size="sm" onClick={onActionClick}>
          {actionText}
        </Button>
      </EmptyContent>
    </Empty>
  );
}
