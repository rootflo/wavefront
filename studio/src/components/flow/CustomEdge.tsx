import React from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  getBezierPath,
  useReactFlow,
} from 'reactflow';
import { Settings, X } from 'lucide-react';
import { useDesignerStore } from '@/store/designerStore';
import { CustomEdgeData } from '@/types/reactflow';

const CustomEdge: React.FC<EdgeProps<CustomEdgeData>> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}) => {
  const { openEdgeEditor, deleteEdge } = useDesignerStore();
  const { getEdge } = useReactFlow();
  
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Generate unique marker ID for this edge
  const markerId = `arrow-${id}`;

  const handleEdit = () => {
    const edge = getEdge(id);
    if (edge) {
      openEdgeEditor(edge);
    }
  };

  const handleDelete = () => {
    deleteEdge(id);
  };

  return (
    <>
      {/* Arrow marker definition */}
      <defs>
        <marker
          id={markerId}
          viewBox="0 0 20 20"
          refX="18"
          refY="10"
          markerWidth="10"
          markerHeight="10"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path
            d="M0,0 L0,20 L20,10 z"
            fill={selected ? '#3b82f6' : '#64748b'}
          />
        </marker>
      </defs>
      
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? '#3b82f6' : '#64748b',
          strokeWidth: selected ? 3 : 2,
          markerEnd: `url(#${markerId})`,
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            position: 'absolute',
            fontSize: 10,
            pointerEvents: 'all',
          }}
          className={`edge-label ${selected ? 'selected' : ''}`}
        >
          <div className="flex items-center gap-2 bg-white border rounded-md shadow-sm px-2 py-1">
            {data?.router && (
              <span className="text-xs text-blue-600 font-medium">
                {data.router}
              </span>
            )}
            <div className="flex items-center gap-1">
              <button
                onClick={handleEdit}
                className="p-1 hover:bg-gray-100 rounded"
                title="Edit router"
              >
                <Settings className="w-3 h-3 text-gray-600" />
              </button>
              <button
                onClick={handleDelete}
                className="p-1 hover:bg-red-100 rounded"
                title="Delete edge"
              >
                <X className="w-3 h-3 text-red-600" />
              </button>
            </div>
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};

export default CustomEdge;
