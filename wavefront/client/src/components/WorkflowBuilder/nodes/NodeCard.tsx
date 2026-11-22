import React from 'react';
import { Trash2 } from 'lucide-react';

interface NodeCardProps {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  colorClass: string;
  selected?: boolean;
  badge?: React.ReactNode;
  onDelete?: () => void;
}

// Common card wrapper for all nodes
export const NodeCard = ({ title, icon: Icon, children, colorClass, selected, badge, onDelete }: NodeCardProps) => {
  return (
    <div
      className={`bg-card w-72 rounded-xl border shadow-md transition-all ${
        selected ? 'border-primary ring-primary/20 shadow-lg ring-2' : 'border-border hover:border-border/80'
      }`}
    >
      <div className={`border-border flex items-center justify-between rounded-t-xl border-b p-3 ${colorClass}`}>
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="bg-background/60 text-foreground flex h-6 w-6 shrink-0 items-center justify-center rounded shadow-xs">
            <Icon size={14} />
          </div>
          <h4 className="text-foreground truncate text-xs font-semibold">{title}</h4>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {badge}
          {onDelete && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              title="Delete node"
              className="text-muted-foreground hover:text-destructive hover:bg-background/50 rounded p-1 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="bg-card/50 flex flex-col gap-2 rounded-b-xl p-3 text-xs">{children}</div>
    </div>
  );
};
