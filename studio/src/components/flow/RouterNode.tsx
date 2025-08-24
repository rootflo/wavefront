import React from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Route, Settings, Zap, GitBranch, RotateCcw, Workflow } from 'lucide-react';
import { RouterNodeData } from '@/types/reactflow';
import { useDesignerStore } from '@/store/designerStore';
import { cn } from '@/lib/utils';

const RouterNode: React.FC<NodeProps<RouterNodeData>> = ({ data, selected, id }) => {
  const { openRouterEditor, deleteNode } = useDesignerStore();
  const { router, isEnd } = data;

  const handleEdit = () => {
    openRouterEditor({
      id,
      type: 'router',
      position: { x: 0, y: 0 },
      data,
    });
  };

  const handleDelete = () => {
    deleteNode(id);
  };

  const getRouterIcon = () => {
    switch (router.type) {
      case 'smart':
        return <Zap className="w-5 h-5 text-purple-600" />;
      case 'task_classifier':
        return <GitBranch className="w-5 h-5 text-purple-600" />;
      case 'conversation_analysis':
        return <Route className="w-5 h-5 text-purple-600" />;
      case 'reflection':
        return <RotateCcw className="w-5 h-5 text-purple-600" />;
      case 'plan_execute':
        return <Workflow className="w-5 h-5 text-purple-600" />;
      default:
        return <Route className="w-5 h-5 text-purple-600" />;
    }
  };

  const getRouterTypeLabel = () => {
    switch (router.type) {
      case 'smart':
        return 'Smart Router';
      case 'task_classifier':
        return 'Task Classifier';
      case 'conversation_analysis':
        return 'Conversation Router';
      case 'reflection':
        return 'Reflection Router';
      case 'plan_execute':
        return 'Plan Execute Router';
      default:
        return 'Custom Router';
    }
  };

  return (
    <div
      className={cn(
        "relative bg-white border-2 rounded-lg shadow-lg min-w-[200px] max-w-[250px]",
        selected ? "border-purple-500" : "border-gray-300",
        isEnd && "border-red-500"
      )}
    >
      {/* Input Handle (Left) */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-4 h-4 !bg-purple-500 !border-2 !border-white"
        style={{ left: -8 }}
      />

      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-gradient-to-r from-purple-50 to-purple-100 rounded-t-lg">
        <div className="flex items-center gap-2">
          {getRouterIcon()}
          <h3 className="font-semibold text-sm text-gray-800 truncate">
            {router.name}
          </h3>
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        <div className="text-xs text-gray-600">
          <span className="font-medium">Type:</span> {getRouterTypeLabel()}
        </div>
        
        {router.model && (
          <div className="text-xs text-gray-600">
            <span className="font-medium">LLM:</span> {router.model.provider}/{router.model.name}
          </div>
        )}

        {router.routing_options && Object.keys(router.routing_options).length > 0 && (
          <div className="text-xs text-gray-600">
            <span className="font-medium">Routes to:</span> {Object.keys(router.routing_options).slice(0, 2).join(', ')}
            {Object.keys(router.routing_options).length > 2 && '...'}
          </div>
        )}

        <div className="text-xs text-gray-500 line-clamp-2">
          {router.description}
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-between p-2 bg-gray-50 rounded-b-lg">
        <button
          onClick={handleEdit}
          className="flex items-center gap-1 px-2 py-1 text-xs text-purple-600 hover:bg-purple-100 rounded"
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

export default RouterNode;
