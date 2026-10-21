import { NODE_TYPES } from '@app/constants/workflow-builder';
import React from 'react';
import { Bot, GitBranch, Plus, Cpu, ArrowRight, Layers } from 'lucide-react';
import { Button } from '@app/components/ui/button';

interface PaletteSectionProps {
  onAddAgent?: () => void;
  onAddRouter?: () => void;
  onAddFunction?: () => void;
  onAddIterator?: () => void;
  onAddSubworkflow?: () => void;
}

const onDragStart = (event: React.DragEvent, nodeType: string, label: string) => {
  event.dataTransfer.setData('application/reactflow', nodeType);
  event.dataTransfer.setData('application/reactflow-label', label);
  event.dataTransfer.effectAllowed = 'move';
};

export const PaletteSection = ({
  onAddAgent,
  onAddRouter,
  onAddFunction,
  onAddIterator,
  onAddSubworkflow,
}: PaletteSectionProps) => (
  <div>
    <span className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-wider uppercase">
      Palette (Drag or Click +)
    </span>
    <div className="space-y-2">
      {/* Agent Button/Draggable */}
      <div
        className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-emerald-500/50 hover:shadow"
        onDragStart={(event) => onDragStart(event, NODE_TYPES.AGENT, 'Agent')}
        draggable
        onClick={onAddAgent}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 font-bold text-emerald-500">
            <Bot size={15} />
          </div>
          <div className="truncate">
            <h4 className="text-foreground text-xs font-semibold">AI Agent</h4>
            <p className="text-muted-foreground truncate text-[10px]">Executes tasks & prompts</p>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-6 w-6 shrink-0 group-hover:text-emerald-500 hover:bg-emerald-500/10"
          onClick={(e) => {
            e.stopPropagation();
            onAddAgent?.();
          }}
          title="Add Agent"
        >
          <Plus size={13} />
        </Button>
      </div>

      {/* Router Button/Draggable */}
      <div
        className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-orange-500/50 hover:shadow"
        onDragStart={(event) => onDragStart(event, NODE_TYPES.ROUTER, 'Router')}
        draggable
        onClick={onAddRouter}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-orange-500/10 font-bold text-orange-500">
            <GitBranch size={15} />
          </div>
          <div className="truncate">
            <h4 className="text-foreground text-xs font-semibold">Router</h4>
            <p className="text-muted-foreground truncate text-[10px]">Smart, Field Match, Loop</p>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-6 w-6 shrink-0 group-hover:text-orange-500 hover:bg-orange-500/10"
          onClick={(e) => {
            e.stopPropagation();
            onAddRouter?.();
          }}
          title="Add Router"
        >
          <Plus size={13} />
        </Button>
      </div>

      {/* Function Button/Draggable */}
      <div
        className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-blue-500/50 hover:shadow"
        onDragStart={(event) => onDragStart(event, NODE_TYPES.FUNCTION, 'Function')}
        draggable
        onClick={onAddFunction}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 font-bold text-blue-500">
            <Cpu size={15} />
          </div>
          <div className="truncate">
            <h4 className="text-foreground text-xs font-semibold">Function Node</h4>
            <p className="text-muted-foreground truncate text-[10px]">Deterministic code logic</p>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-6 w-6 shrink-0 group-hover:text-blue-500 hover:bg-blue-500/10"
          onClick={(e) => {
            e.stopPropagation();
            onAddFunction?.();
          }}
          title="Add Function"
        >
          <Plus size={13} />
        </Button>
      </div>

      {/* Iterator Button/Draggable */}
      <div
        className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-indigo-500/50 hover:shadow"
        onDragStart={(event) => onDragStart(event, NODE_TYPES.ITERATOR, 'Iterator')}
        draggable
        onClick={onAddIterator}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 font-bold text-indigo-500">
            <ArrowRight size={15} />
          </div>
          <div className="truncate">
            <h4 className="text-foreground text-xs font-semibold">ForEach Iterator</h4>
            <p className="text-muted-foreground truncate text-[10px]">Loop over lists/items</p>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-6 w-6 shrink-0 group-hover:text-indigo-500 hover:bg-indigo-500/10"
          onClick={(e) => {
            e.stopPropagation();
            onAddIterator?.();
          }}
          title="Add Iterator"
        >
          <Plus size={13} />
        </Button>
      </div>

      {/* Sub-Workflow Button/Draggable */}
      <div
        className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-teal-500/50 hover:shadow"
        onDragStart={(event) => onDragStart(event, NODE_TYPES.SUBWORKFLOW, 'Sub-Workflow')}
        draggable
        onClick={onAddSubworkflow}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-500/10 font-bold text-teal-500">
            <Layers size={15} />
          </div>
          <div className="truncate">
            <h4 className="text-foreground text-xs font-semibold">Sub-Workflow</h4>
            <p className="text-muted-foreground truncate text-[10px]">Nested arium workflow</p>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-6 w-6 shrink-0 group-hover:text-teal-500 hover:bg-teal-500/10"
          onClick={(e) => {
            e.stopPropagation();
            onAddSubworkflow?.();
          }}
          title="Add Sub-Workflow"
        >
          <Plus size={13} />
        </Button>
      </div>
    </div>
  </div>
);
