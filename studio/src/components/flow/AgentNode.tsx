import React from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Bot, Settings, Play, Square } from 'lucide-react';
import { AgentNodeData } from '@/types/reactflow';
import { useDesignerStore } from '@/store/designerStore';
import { cn } from '@/lib/utils';

const AgentNode: React.FC<NodeProps<AgentNodeData>> = ({ data, selected, id }) => {
  const { 
    openAgentEditor, 
    deleteNode, 
    startNodeId, 
    endNodeIds
  } = useDesignerStore();
  const { agent } = data;
  
  const isStart = startNodeId === id;
  const isEnd = endNodeIds.includes(id);

  const handleEdit = () => {
    openAgentEditor({
      id,
      type: 'agent',
      position: { x: 0, y: 0 },
      data,
    });
  };

  const handleDelete = () => {
    deleteNode(id);
  };

  return (
    <div
      className={cn(
        "relative bg-white border-2 rounded-lg shadow-lg min-w-[200px] max-w-[250px]",
        selected ? "border-blue-500" : "border-gray-300",
        isStart && "border-green-500",
        isEnd && "border-red-500"
      )}
    >
      {/* Input Handle (Left) */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-4 h-4 !bg-blue-500 !border-2 !border-white"
        style={{ left: -8 }}
      />

      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-gradient-to-r from-blue-50 to-blue-100 rounded-t-lg">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-600" />
          <h3 className="font-semibold text-sm text-gray-800 truncate">
            {agent.name}
          </h3>
        </div>
        <div className="flex items-center gap-1">
          {isStart && (
            <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full flex items-center gap-1">
              <Play className="w-3 h-3" />
              Start
            </span>
          )}
          {isEnd && (
            <span className="px-2 py-1 bg-red-100 text-red-800 text-xs font-medium rounded-full flex items-center gap-1">
              <Square className="w-3 h-3" />
              End
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        {agent.role && (
          <div className="text-xs text-gray-600">
            <span className="font-medium">Role:</span> {agent.role}
          </div>
        )}
        
        <div className="text-xs text-gray-600">
          <span className="font-medium">LLM:</span> {agent.model.provider}/{agent.model.name}
        </div>

        {agent.tools && agent.tools.length > 0 && (
          <div className="text-xs text-gray-600">
            <span className="font-medium">Tools:</span> {agent.tools.slice(0, 2).join(', ')}
            {agent.tools.length > 2 && '...'}
          </div>
        )}

        <div className="text-xs text-gray-500 line-clamp-2">
          {agent.job}
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-between p-2 bg-gray-50 rounded-b-lg">
        <button
          onClick={handleEdit}
          className="flex items-center gap-1 px-2 py-1 text-xs text-blue-600 hover:bg-blue-100 rounded"
        >
          <Settings className="w-3 h-3" />
          Edit
        </button>
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
        className="w-4 h-4 !bg-green-500 !border-2 !border-white"
        style={{ right: -8 }}
      />
    </div>
  );
};

export default AgentNode;
