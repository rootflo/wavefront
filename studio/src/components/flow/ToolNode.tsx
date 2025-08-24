import React from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Wrench, Square } from 'lucide-react';
import { ToolNodeData } from '@/types/reactflow';
import { useDesignerStore } from '@/store/designerStore';
import { cn } from '@/lib/utils';

const ToolNode: React.FC<NodeProps<ToolNodeData>> = ({ data, selected, id }) => {
  const { deleteNode } = useDesignerStore();
  const { tool, isEnd } = data;

  const handleDelete = () => {
    deleteNode(id);
  };

  return (
    <div
      className={cn(
        "relative bg-white border-2 rounded-lg shadow-lg min-w-[180px] max-w-[220px]",
        selected ? "border-orange-500" : "border-gray-300",
        isEnd && "border-red-500"
      )}
    >
      {/* Input Handle (Left) */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-4 h-4 !bg-orange-500 !border-2 !border-white"
        style={{ left: -8 }}
      />

      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-gradient-to-r from-orange-50 to-orange-100 rounded-t-lg">
        <div className="flex items-center gap-2">
          <Wrench className="w-5 h-5 text-orange-600" />
          <h3 className="font-semibold text-sm text-gray-800 truncate">
            {tool.name}
          </h3>
        </div>
        <div className="flex items-center gap-1">
          {isEnd && <Square className="w-4 h-4 text-red-600" />}
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        <div className="text-xs text-gray-500 line-clamp-3">
          {tool.description}
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end p-2 bg-gray-50 rounded-b-lg">
        <button
          onClick={handleDelete}
          className="flex items-center gap-1 px-2 py-1 text-xs text-red-600 hover:bg-red-100 rounded"
        >
          ×
        </button>
      </div>

      {/* Output Handle (Right) */}
      <Handle
        type="source"
        position={Position.Right}
        className="w-4 h-4 !bg-orange-500 !border-2 !border-white"
        style={{ right: -8 }}
      />
    </div>
  );
};

export default ToolNode;
