import { AlertTriangle, CircleAlert, X } from 'lucide-react';
import React from 'react';

export interface Problem {
  // Where the problem is (e.g. a YAML path or node name); optional
  location?: string;
  message: string;
}

interface ProblemsPanelProps {
  title: string;
  problems: Problem[];
  // error: blocks the action (e.g. save); warning: informational
  tone?: 'error' | 'warning';
  onDismiss?: () => void;
  maxVisible?: number;
  className?: string;
}

const TONE_STYLES = {
  error: { icon: CircleAlert, accent: 'border-destructive/50', iconColor: 'text-destructive' },
  warning: { icon: AlertTriangle, accent: 'border-amber-500/50', iconColor: 'text-amber-500' },
};

// Persistent list of problems with the current draft. Unlike toasts it stays until the problems are fixed or it is
// dismissed, and it uses an opaque surface so it stays readable over the canvas.
export const ProblemsPanel: React.FC<ProblemsPanelProps> = ({
  title,
  problems,
  tone = 'error',
  onDismiss,
  maxVisible,
  className = '',
}) => {
  if (problems.length === 0) return null;
  const { icon: Icon, accent, iconColor } = TONE_STYLES[tone];
  const visible = maxVisible ? problems.slice(0, maxVisible) : problems;
  const hidden = problems.length - visible.length;

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`bg-background text-foreground w-[28rem] max-w-[calc(100vw-2rem)] rounded-lg border shadow-xl ${accent} ${className}`}
    >
      <div className="flex items-start gap-2 px-4 pt-3 pb-2">
        <Icon size={16} className={`mt-0.5 shrink-0 ${iconColor}`} />
        <p className="flex-1 text-sm font-semibold">{title}</p>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="text-muted-foreground hover:text-foreground hover:bg-muted -mt-0.5 -mr-1 rounded p-1"
          >
            <X size={14} />
          </button>
        )}
      </div>
      <ul className="max-h-64 space-y-2 overflow-y-auto px-4 pb-3 pl-10">
        {visible.map((problem, index) => (
          <li key={`${problem.location ?? ''}-${index}`} className="text-sm leading-snug">
            <span className="break-words">{problem.message}</span>
            {problem.location && (
              <span className="text-muted-foreground mt-0.5 block font-mono text-xs break-all">{problem.location}</span>
            )}
          </li>
        ))}
      </ul>
      {hidden > 0 && <p className="text-muted-foreground px-4 pb-3 pl-10 text-xs">and {hidden} more</p>}
    </div>
  );
};
