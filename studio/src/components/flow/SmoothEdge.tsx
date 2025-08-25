import React from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  getSmoothStepPath,
} from 'reactflow';
import { Route } from 'lucide-react';

import { CustomEdgeData } from '@/types/reactflow';

const SmoothEdge: React.FC<EdgeProps<CustomEdgeData>> = ({
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
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 20,
    offset: 20,
  });

  // Generate unique marker ID for this edge
  const markerId = `arrow-smooth-${id}`;



  // Determine edge color based on router type
  const getEdgeColor = () => {
    if (!data?.router) return selected ? '#3b82f6' : '#64748b';
    
    if (data.router.includes('reflection')) return selected ? '#9333ea' : '#a855f7';
    if (data.router.includes('plan_execute')) return selected ? '#ea580c' : '#f97316';
    return selected ? '#059669' : '#10b981';
  };

  const edgeColor = getEdgeColor();

  return (
    <>
      {/* Arrow marker definition */}
      <defs>
        <marker
          id={markerId}
          viewBox="0 0 20 20"
          refX="18"
          refY="10"
          markerWidth="12"
          markerHeight="12"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path
            d="M0,0 L0,20 L20,10 z"
            fill={edgeColor}
          />
        </marker>
      </defs>
      
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: edgeColor,
          strokeWidth: selected ? 3 : 2,
          markerEnd: `url(#${markerId})`,
          filter: selected ? 'drop-shadow(0 4px 6px rgb(0 0 0 / 0.1))' : undefined,
        }}
      />
      
      {/* Only show label when there's a router */}
      {data?.router && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              position: 'absolute',
              fontSize: 10,
              pointerEvents: 'none',
            }}
            className="edge-label"
          >
            <div className="flex items-center gap-1 bg-white border rounded-lg shadow-md px-3 py-2">
              <Route className="w-3 h-3" style={{ color: edgeColor }} />
              <span className="text-xs font-medium" style={{ color: edgeColor }}>
                {data.router.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export default SmoothEdge;
