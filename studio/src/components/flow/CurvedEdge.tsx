import React from 'react';
import {
  BaseEdge,
  EdgeProps,
  getBezierPath,
} from 'reactflow';
import { CustomEdgeData } from '@/types/reactflow';

const CurvedEdge: React.FC<EdgeProps<CustomEdgeData>> = ({
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
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.25,
  });

  // Generate unique marker ID for this edge
  const markerId = `arrow-curved-${id}`;

  const edgeColor = selected ? '#3b82f6' : '#94a3b8';

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
            fill={edgeColor}
          />
        </marker>
      </defs>
      
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: edgeColor,
          strokeWidth: selected ? 2.5 : 1.5,
          markerEnd: `url(#${markerId})`,
          strokeDasharray: '5,5',
          opacity: 0.8,
        }}
      />

    </>
  );
};

export default CurvedEdge;
