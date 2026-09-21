import { Button } from '@app/components/ui/button';
import { App } from '@app/types/app';
import { formatAppName } from '@app/lib/utils';
import dayjs from 'dayjs';
import { Pencil, Trash2 } from 'lucide-react';
import React from 'react';
import { useNavigate } from 'react-router';

interface AppCardProps {
  app: App;
  onClick: (app: App) => void;
  onDeleteClick: (app: App) => void;
}

const cardIconButtonClass = 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100';

/** Compact glass tile shell for app listing. */
const appCardShell =
  'group relative flex min-h-[80px] w-full cursor-pointer flex-col justify-between gap-3 overflow-hidden rounded-lg border border-white/30 bg-white/15 p-3.5 shadow-[0_6px_20px_-10px_rgba(15,23,42,0.16)] ring-1 ring-white/20 backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:bg-white/25 dark:border-white/[0.06] dark:bg-white/[0.04] dark:shadow-[0_6px_20px_-10px_rgba(0,0,0,0.45)] dark:ring-white/[0.05] dark:hover:bg-white/[0.08]';

const AppCard: React.FC<AppCardProps> = ({ app, onClick, onDeleteClick }) => {
  const navigate = useNavigate();

  const handleEditApp = (target: App) => {
    navigate(`/apps/edit/${target.id}`);
  };

  return (
    <div
      className={appCardShell}
      onClick={(e) => {
        e.preventDefault();
        onClick(app);
      }}
    >
      <div className="absolute top-2.5 right-2.5 z-10 flex items-center gap-0.5">
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          title="Edit"
          aria-label="Edit"
          className={cardIconButtonClass}
          onClick={(e) => {
            e.stopPropagation();
            handleEditApp(app);
          }}
        >
          <Pencil className="size-3" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          title="Delete"
          aria-label="Delete"
          className={cardIconButtonClass}
          onClick={(e) => {
            e.stopPropagation();
            onDeleteClick(app);
          }}
        >
          <Trash2 className="size-3" />
        </Button>
      </div>

      <div className="relative pr-12">
        <p className="frost-text truncate text-[15px] font-medium tracking-normal normal-case transition-colors group-hover:text-slate-700 dark:group-hover:text-slate-100">
          {formatAppName(app.app_name)}
        </p>
        <p className="frost-text-muted mt-0.5 truncate text-[11px] font-normal tracking-normal normal-case">
          {app.public_url}
        </p>
      </div>
      <div className="frost-text-subtle relative text-[10px] font-normal tracking-normal normal-case">
        Updated {dayjs(app.updated_at || app.created_at).format('DD/MM/YYYY')}
      </div>
    </div>
  );
};

export default AppCard;

export { appCardShell };
