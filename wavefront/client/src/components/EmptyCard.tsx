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
    <Empty className="frost-card ring-frost-border relative overflow-hidden border border-dashed ring-1">
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />
      <EmptyHeader className="relative">
        <EmptyTitle className="frost-text text-[15px] font-medium tracking-normal normal-case">{title}</EmptyTitle>
        <EmptyDescription className="frost-text-muted text-[13px] font-normal tracking-normal normal-case">
          {description}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent className="relative">
        <Button variant="outline" size="sm" className="normal-case" onClick={onActionClick}>
          {actionText}
        </Button>
      </EmptyContent>
    </Empty>
  );
}
