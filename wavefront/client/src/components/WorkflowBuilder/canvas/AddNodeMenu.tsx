import { Bot, GitBranch, Cpu, ArrowRight, Layers, LucideIcon } from 'lucide-react';
import { AddableNodeType, NODE_TYPES } from '@app/constants/workflow-builder';

export interface AddNodeMenuState {
  x: number;
  y: number;
  sourceId: string;
}

interface QuickAddOption {
  type: AddableNodeType;
  label: string;
  icon: LucideIcon;
  // Full literal class strings so Tailwind can detect them
  className: string;
}

const QUICK_ADD_OPTIONS: QuickAddOption[] = [
  {
    type: NODE_TYPES.AGENT,
    label: '+ Add Agent',
    icon: Bot,
    className:
      'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-emerald-600 transition-colors hover:bg-emerald-500/10 dark:text-emerald-400',
  },
  {
    type: NODE_TYPES.ROUTER,
    label: '+ Add Router',
    icon: GitBranch,
    className:
      'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-orange-600 transition-colors hover:bg-orange-500/10 dark:text-orange-400',
  },
  {
    type: NODE_TYPES.FUNCTION,
    label: '+ Add Function',
    icon: Cpu,
    className:
      'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-blue-600 transition-colors hover:bg-blue-500/10 dark:text-blue-400',
  },
  {
    type: NODE_TYPES.ITERATOR,
    label: '+ Add Iterator',
    icon: ArrowRight,
    className:
      'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-500/10 dark:text-indigo-400',
  },
  {
    type: NODE_TYPES.SUBWORKFLOW,
    label: '+ Add Sub-Workflow',
    icon: Layers,
    className:
      'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-teal-600 transition-colors hover:bg-teal-500/10 dark:text-teal-400',
  },
];

interface AddNodeMenuProps {
  menu: AddNodeMenuState;
  onQuickAdd: (type: AddableNodeType) => void;
}

// Quick add popup (on dragging an edge into empty canvas)
export const AddNodeMenu = ({ menu, onQuickAdd }: AddNodeMenuProps) => (
  <div
    className="bg-card border-border animate-in fade-in zoom-in-95 absolute z-50 flex w-52 flex-col gap-1 rounded-xl border p-2 shadow-xl duration-100"
    style={{ top: Math.max(10, menu.y - 140), left: Math.max(10, menu.x - 290) }}
  >
    <div className="text-muted-foreground px-2 py-1 text-[10px] font-bold tracking-wider uppercase">Quick Add Step</div>
    {QUICK_ADD_OPTIONS.map(({ type, label, icon: Icon, className }) => (
      <button key={type} className={className} onClick={() => onQuickAdd(type)}>
        <Icon size={13} /> {label}
      </button>
    ))}
  </div>
);
