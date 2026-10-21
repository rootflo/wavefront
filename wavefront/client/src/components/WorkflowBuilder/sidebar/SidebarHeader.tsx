import { PanelLeftClose } from 'lucide-react';

interface SidebarHeaderProps {
  onCollapse: () => void;
}

export const SidebarHeader = ({ onCollapse }: SidebarHeaderProps) => (
  <div className="border-border bg-muted/10 flex items-center justify-between border-b p-3">
    <div>
      <h3 className="text-foreground text-xs font-semibold tracking-wider uppercase">Components & Outline</h3>
      <p className="text-muted-foreground mt-0.5 text-[11px]">Add or jump to workflow steps</p>
    </div>
    <button
      onClick={onCollapse}
      className="hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg p-1 transition-colors"
      title="Collapse Sidebar to maximize canvas"
    >
      <PanelLeftClose size={15} />
    </button>
  </div>
);
