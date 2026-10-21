import { Trash2 } from 'lucide-react';
import { Node } from '@xyflow/react';
import { Badge } from '@app/components/ui/badge';
import { getNodeTypeStyle } from './nodeTypeStyles';

interface OutlineItemProps {
  node: Node;
  isSelected: boolean;
  isStart: boolean;
  onSelectNode?: (nodeId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
}

export const OutlineItem = ({ node, isSelected, isStart, onSelectNode, onDeleteNode }: OutlineItemProps) => {
  const { icon: IconComponent, iconColor, activeBg } = getNodeTypeStyle(node.type);

  return (
    <div
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
          <Badge className="shrink-0 border-none bg-emerald-500/20 px-1 py-0 text-[8px] text-emerald-500">Start</Badge>
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
};
