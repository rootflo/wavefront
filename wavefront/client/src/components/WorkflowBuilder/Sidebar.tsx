import React from 'react';
import { Node } from '@xyflow/react';
import { CollapsedSidebar } from './sidebar/CollapsedSidebar';
import { SidebarHeader } from './sidebar/SidebarHeader';
import { PaletteSection } from './sidebar/PaletteSection';
import { EntryStepSection } from './sidebar/EntryStepSection';
import { OutlineSection } from './sidebar/OutlineSection';

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

  if (collapsed) {
    return (
      <CollapsedSidebar
        onExpand={() => setCollapsed(false)}
        onAddAgent={onAddAgent}
        onAddRouter={onAddRouter}
        onAddFunction={onAddFunction}
        onAddIterator={onAddIterator}
        onAddSubworkflow={onAddSubworkflow}
      />
    );
  }

  return (
    <aside className="border-border bg-card z-10 flex h-full w-64 shrink-0 flex-col border-r shadow-xs max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-20">
      <SidebarHeader onCollapse={() => setCollapsed(true)} />

      <div className="flex-1 space-y-5 overflow-y-auto p-3">
        <PaletteSection
          onAddAgent={onAddAgent}
          onAddRouter={onAddRouter}
          onAddFunction={onAddFunction}
          onAddIterator={onAddIterator}
          onAddSubworkflow={onAddSubworkflow}
        />
        <EntryStepSection nodes={nodes} startAgentName={startAgentName} onSetStartAgent={onSetStartAgent} />
        <OutlineSection
          nodes={nodes}
          selectedNodeId={selectedNodeId}
          startAgentName={startAgentName}
          onSelectNode={onSelectNode}
          onDeleteNode={onDeleteNode}
        />
      </div>
    </aside>
  );
};
