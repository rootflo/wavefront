import React from 'react';
import { Bot, GitBranch, Plus, Trash2, Cpu, ArrowRight, Layers, PanelLeft, PanelLeftClose } from 'lucide-react';
import { Button } from '@app/components/ui/button';
import { Badge } from '@app/components/ui/badge';
import { Node } from '@xyflow/react';

interface SidebarProps {
  nodes?: Node[];
  selectedNodeId?: string;
  startAgentName?: string;
  onSelectNode?: (nodeId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
  onAddAgent?: () => void;
  onAddRouter?: () => void;
  onAddFunction?: () => void;
  onAddIterator?: () => void;
  onAddSubworkflow?: () => void;
  onSetStartAgent?: (agentName: string) => void;
}

export const Sidebar = ({
  nodes = [],
  selectedNodeId,
  startAgentName,
  onSelectNode,
  onDeleteNode,
  onAddAgent,
  onAddRouter,
  onAddFunction,
  onAddIterator,
  onAddSubworkflow,
  onSetStartAgent,
}: SidebarProps) => {
  const [collapsed, setCollapsed] = React.useState(false);

  const onDragStart = (event: React.DragEvent, nodeType: string, label: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow-label', label);
    event.dataTransfer.effectAllowed = 'move';
  };

  if (collapsed) {
    return (
      <aside className="border-border bg-card z-10 flex h-full w-12 shrink-0 flex-col items-center gap-2 border-r py-3 shadow-xs">
        <button
          onClick={() => setCollapsed(false)}
          className="hover:bg-muted text-muted-foreground hover:text-foreground mb-1 rounded-lg p-1.5 transition-colors"
          title="Expand Components & Outline"
        >
          <PanelLeft size={16} />
        </button>
        <div className="bg-border my-0.5 h-[1px] w-6" />
        <button
          onClick={onAddAgent}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 transition-colors hover:bg-emerald-500/20 dark:text-emerald-400"
          title="Add AI Agent"
        >
          <Bot size={15} />
        </button>
        <button
          onClick={onAddRouter}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-500/10 text-orange-600 transition-colors hover:bg-orange-500/20 dark:text-orange-400"
          title="Add Router"
        >
          <GitBranch size={15} />
        </button>
        <button
          onClick={onAddFunction}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 transition-colors hover:bg-blue-500/20 dark:text-blue-400"
          title="Add Function"
        >
          <Cpu size={15} />
        </button>
        <button
          onClick={onAddIterator}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-600 transition-colors hover:bg-indigo-500/20 dark:text-indigo-400"
          title="Add Iterator"
        >
          <ArrowRight size={15} />
        </button>
        <button
          onClick={onAddSubworkflow}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10 text-teal-600 transition-colors hover:bg-teal-500/20 dark:text-teal-400"
          title="Add Sub-Workflow"
        >
          <Layers size={15} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="border-border bg-card z-10 flex h-full w-64 shrink-0 flex-col border-r shadow-xs">
      {/* Header */}
      <div className="border-border bg-muted/10 flex items-center justify-between border-b p-3">
        <div>
          <h3 className="text-foreground text-xs font-semibold tracking-wider uppercase">Components & Outline</h3>
          <p className="text-muted-foreground mt-0.5 text-[11px]">Add or jump to workflow steps</p>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg p-1 transition-colors"
          title="Collapse Sidebar to maximize canvas"
        >
          <PanelLeftClose size={15} />
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-3">
        {/* SECTION 1: ADDABLE PALETTE */}
        <div>
          <span className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-wider uppercase">
            Palette (Drag or Click +)
          </span>
          <div className="space-y-2">
            {/* Agent Button/Draggable */}
            <div
              className="border-border bg-background group flex cursor-grab items-center justify-between rounded-xl border p-2 shadow-xs transition-all hover:border-emerald-500/50 hover:shadow"
              onDragStart={(event) => onDragStart(event, 'agentNode', 'Agent')}
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
              onDragStart={(event) => onDragStart(event, 'routerNode', 'Router')}
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
              onDragStart={(event) => onDragStart(event, 'functionNode', 'Function')}
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
              onDragStart={(event) => onDragStart(event, 'iteratorNode', 'Iterator')}
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
              onDragStart={(event) => onDragStart(event, 'subworkflowNode', 'Sub-Workflow')}
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

        {/* SECTION 2: WORKFLOW ENTRY STEP */}
        <div className="bg-muted/20 border-border rounded-xl border p-2.5">
          <span className="text-muted-foreground mb-1.5 block text-[10px] font-bold tracking-wider uppercase">
            ⚡ Workflow Entry Agent
          </span>
          <select
            className="bg-background border-border text-foreground focus:border-primary w-full rounded-md border px-2 py-1 text-xs focus:outline-none"
            value={startAgentName || ''}
            onChange={(e) => onSetStartAgent?.(e.target.value)}
          >
            {nodes.filter((n) => n.type !== 'triggerNode').length === 0 && <option value="">No steps on canvas</option>}
            {nodes
              .filter((n) => n.type !== 'triggerNode')
              .map((node) => (
                <option key={node.id} value={node.id}>
                  🚀 {(node.data?.label as string) || node.id}{' '}
                  {(node.data?.role as string) ? `(${node.data.role})` : ''}
                </option>
              ))}
          </select>
        </div>

        {/* SECTION 3: CANVAS OUTLINE & QUICK NAVIGATION */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-muted-foreground text-[10px] font-bold tracking-wider uppercase">
              Outline ({nodes.length} nodes)
            </span>
          </div>

          <div className="space-y-1">
            {nodes
              .filter((n) => n.type !== 'triggerNode')
              .map((node) => {
                const isSelected = selectedNodeId === node.id;
                const isStart = startAgentName === node.id;

                let IconComponent = Bot;
                let iconColor = 'text-emerald-500';
                let activeBg = 'border-emerald-500 bg-emerald-500/10';

                if (node.type === 'routerNode') {
                  IconComponent = GitBranch;
                  iconColor = 'text-orange-500';
                  activeBg = 'border-orange-500 bg-orange-500/10';
                } else if (node.type === 'functionNode') {
                  IconComponent = Cpu;
                  iconColor = 'text-blue-500';
                  activeBg = 'border-blue-500 bg-blue-500/10';
                } else if (node.type === 'iteratorNode') {
                  IconComponent = ArrowRight;
                  iconColor = 'text-indigo-500';
                  activeBg = 'border-indigo-500 bg-indigo-500/10';
                } else if (node.type === 'subworkflowNode') {
                  IconComponent = Layers;
                  iconColor = 'text-teal-500';
                  activeBg = 'border-teal-500 bg-teal-500/10';
                }

                return (
                  <div
                    key={node.id}
                    onClick={() => onSelectNode?.(node.id)}
                    className={`flex cursor-pointer items-center justify-between rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                      isSelected
                        ? `${activeBg} text-foreground font-semibold`
                        : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <IconComponent size={13} className={`${iconColor} shrink-0`} />
                      <span className="truncate">{(node.data?.label as string) || node.id}</span>
                      {isStart && (
                        <Badge className="shrink-0 border-none bg-emerald-500/20 px-1 py-0 text-[8px] text-emerald-500">
                          Start
                        </Badge>
                      )}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteNode?.(node.id);
                      }}
                      title="Delete step"
                      className="text-muted-foreground/60 hover:text-destructive hover:bg-background shrink-0 rounded p-0.5"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                );
              })}

            {nodes.length === 0 && (
              <p className="text-muted-foreground py-4 text-center text-[11px] italic">
                Canvas is empty. Click + to add components.
              </p>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
};
