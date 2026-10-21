import { Bot, GitBranch, Cpu, ArrowRight, Layers, PanelLeft } from 'lucide-react';

interface CollapsedSidebarProps {
  onExpand: () => void;
  onAddAgent?: () => void;
  onAddRouter?: () => void;
  onAddFunction?: () => void;
  onAddIterator?: () => void;
  onAddSubworkflow?: () => void;
}

export const CollapsedSidebar = ({
  onExpand,
  onAddAgent,
  onAddRouter,
  onAddFunction,
  onAddIterator,
  onAddSubworkflow,
}: CollapsedSidebarProps) => (
  <aside className="border-border bg-card z-10 flex h-full w-12 shrink-0 flex-col items-center gap-2 border-r py-3 shadow-xs">
    <button
      type="button"
      onClick={onExpand}
      className="hover:bg-muted text-muted-foreground hover:text-foreground mb-1 rounded-lg p-1.5 transition-colors"
      title="Expand Components & Outline"
    >
      <PanelLeft size={16} />
    </button>
    <div className="bg-border my-0.5 h-[1px] w-6" />
    <button
      type="button"
      onClick={onAddAgent}
      className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 transition-colors hover:bg-emerald-500/20 dark:text-emerald-400"
      title="Add AI Agent"
    >
      <Bot size={15} />
    </button>
    <button
      type="button"
      onClick={onAddRouter}
      className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-500/10 text-orange-600 transition-colors hover:bg-orange-500/20 dark:text-orange-400"
      title="Add Router"
    >
      <GitBranch size={15} />
    </button>
    <button
      type="button"
      onClick={onAddFunction}
      className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 transition-colors hover:bg-blue-500/20 dark:text-blue-400"
      title="Add Function"
    >
      <Cpu size={15} />
    </button>
    <button
      type="button"
      onClick={onAddIterator}
      className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-600 transition-colors hover:bg-indigo-500/20 dark:text-indigo-400"
      title="Add Iterator"
    >
      <ArrowRight size={15} />
    </button>
    <button
      type="button"
      onClick={onAddSubworkflow}
      className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10 text-teal-600 transition-colors hover:bg-teal-500/20 dark:text-teal-400"
      title="Add Sub-Workflow"
    >
      <Layers size={15} />
    </button>
  </aside>
);
