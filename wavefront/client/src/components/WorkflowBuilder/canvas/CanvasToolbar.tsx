import { Node } from '@xyflow/react';
import { Sparkles, Bot, GitBranch, Cpu, ArrowRight, Layers, Maximize2, Filter } from 'lucide-react';
import { Button } from '@app/components/ui/button';
import { Badge } from '@app/components/ui/badge';

interface CanvasToolbarProps {
  nodes: Node[];
  startAgentName: string;
  showDataWires: boolean;
  onAddAgent: () => void;
  onAddRouter: () => void;
  onAddFunction: () => void;
  onAddIterator: () => void;
  onAddSubworkflow: () => void;
  onAutoLayout: () => void;
  onToggleDataWires: () => void;
  onFitView: () => void;
}

// Floating action toolbar at the top of the canvas
export const CanvasToolbar = ({
  nodes,
  startAgentName,
  showDataWires,
  onAddAgent,
  onAddRouter,
  onAddFunction,
  onAddIterator,
  onAddSubworkflow,
  onAutoLayout,
  onToggleDataWires,
  onFitView,
}: CanvasToolbarProps) => (
  <div className="bg-card/95 border-border absolute top-3 left-4 z-20 flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 shadow-md backdrop-blur-md">
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onAddAgent}
      className="h-7 gap-1 border-emerald-500/30 text-xs font-medium text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
    >
      <Bot size={13} /> + Agent
    </Button>
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onAddRouter}
      className="h-7 gap-1 border-orange-500/30 text-xs font-medium text-orange-600 hover:bg-orange-500/10 dark:text-orange-400"
    >
      <GitBranch size={13} /> + Router
    </Button>
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onAddFunction}
      className="h-7 gap-1 border-blue-500/30 text-xs font-medium text-blue-600 hover:bg-blue-500/10 dark:text-blue-400"
    >
      <Cpu size={13} /> + Function
    </Button>
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onAddIterator}
      className="h-7 gap-1 border-indigo-500/30 text-xs font-medium text-indigo-600 hover:bg-indigo-500/10 dark:text-indigo-400"
    >
      <ArrowRight size={13} /> + Iterator
    </Button>
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onAddSubworkflow}
      className="h-7 gap-1 border-teal-500/30 text-xs font-medium text-teal-600 hover:bg-teal-500/10 dark:text-teal-400"
    >
      <Layers size={13} /> + Sub-Flow
    </Button>

    <div className="bg-border mx-1 my-auto h-4 w-[1px]" />

    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={onAutoLayout}
      className="text-muted-foreground hover:text-foreground h-7 gap-1 text-xs font-medium"
      title="Automatically align and organize all blocks horizontally with zero overlap"
    >
      <Sparkles size={13} /> Re-align
    </Button>

    <Button
      type="button"
      size="sm"
      variant={showDataWires ? 'secondary' : 'ghost'}
      onClick={onToggleDataWires}
      className={`h-7 gap-1 text-xs font-medium ${
        showDataWires
          ? 'border border-blue-500/30 bg-blue-500/10 text-blue-500'
          : 'text-muted-foreground hover:text-foreground'
      }`}
      title={showDataWires ? 'Hide background memory wires (show only focused)' : 'Show all memory filter wires'}
    >
      <Filter size={12} /> {showDataWires ? 'Data Wires: All' : 'Data Wires: Focus'}
    </Button>

    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={onFitView}
      className="text-muted-foreground hover:text-foreground h-7 gap-1 text-xs font-medium"
      title="Fit entire flow to screen"
    >
      <Maximize2 size={13} /> Fit
    </Button>

    {startAgentName && (
      <Badge
        variant="outline"
        className="ml-1 border-emerald-500/30 bg-emerald-500/10 py-0.5 text-[10px] text-emerald-600 dark:text-emerald-400"
      >
        🚀 Start: {(nodes.find((n) => n.id === startAgentName)?.data?.label as string) || startAgentName}
      </Badge>
    )}
  </div>
);
