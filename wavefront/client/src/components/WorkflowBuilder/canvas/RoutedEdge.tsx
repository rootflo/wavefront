import { memo } from 'react';
import { BaseEdge, EdgeProps, getSmoothStepPath, useInternalNode } from '@xyflow/react';
import type { XYPosition } from '@xyflow/react';
import { EdgeRoute } from '../autoLayout';
import { useLayoutDirection } from '../hooks/useWorkflowActions';

const POSITION_TOLERANCE = 1;

const near = (a: XYPosition, b: XYPosition) =>
  Math.abs(a.x - b.x) <= POSITION_TOLERANCE && Math.abs(a.y - b.y) <= POSITION_TOLERANCE;

// Cubic segments that leave and enter every waypoint along the flow axis, so the curve passes through all of them
// (the gaps between blocks the layout reserved) without overshooting
const buildPath = (points: XYPosition[], vertical: boolean): string => {
  let path = `M ${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (vertical) {
      const dy = (b.y - a.y) / 2;
      path += ` C ${a.x},${a.y + dy} ${b.x},${b.y - dy} ${b.x},${b.y}`;
    } else {
      const dx = (b.x - a.x) / 2;
      path += ` C ${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
    }
  }
  return path;
};

// Draws an edge along the route the auto-layout computed around the blocks. After either end is dragged away from the
// layout the route no longer holds, so it falls back to a smoothstep curve until the next Auto-Layout.
export const RoutedEdge = memo(
  ({
    source,
    target,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    style,
    markerEnd,
    label,
    labelStyle,
    labelBgStyle,
    labelBgPadding,
    labelBgBorderRadius,
    interactionWidth,
  }: EdgeProps) => {
    const sourceNode = useInternalNode(source);
    const targetNode = useInternalNode(target);
    const direction = useLayoutDirection();
    const route = data?.route as EdgeRoute | undefined;

    const routeHolds =
      !!route &&
      route.points.length >= 2 &&
      !!sourceNode &&
      !!targetNode &&
      near(sourceNode.internals.positionAbsolute, route.sourcePosition) &&
      near(targetNode.internals.positionAbsolute, route.targetPosition);

    let path: string;
    let labelX: number;
    let labelY: number;
    if (routeHolds && route) {
      // Pin the ends to the real handles; the waypoints in between come from the layout
      const points = [{ x: sourceX, y: sourceY }, ...route.points.slice(1, -1), { x: targetX, y: targetY }];
      path = buildPath(points, direction === 'TB');
      const middle = route.labelPosition ?? points[Math.floor(points.length / 2)];
      labelX = middle.x;
      labelY = middle.y;
    } else {
      [path, labelX, labelY] = getSmoothStepPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
        borderRadius: 12,
      });
    }

    return (
      <BaseEdge
        path={path}
        labelX={labelX}
        labelY={labelY}
        label={label}
        labelStyle={labelStyle}
        labelBgStyle={labelBgStyle}
        labelBgPadding={labelBgPadding}
        labelBgBorderRadius={labelBgBorderRadius}
        labelShowBg
        markerEnd={markerEnd}
        style={style}
        interactionWidth={interactionWidth}
      />
    );
  }
);
RoutedEdge.displayName = 'RoutedEdge';
