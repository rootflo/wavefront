import { Position } from '@xyflow/react';
import type { CSSProperties } from 'react';

// Canvas flow direction: left-to-right (default) or top-to-bottom. Positions aren't stored in the YAML,
// so the choice is a per-browser preference.
export type LayoutDirection = 'LR' | 'TB';

export const DEFAULT_LAYOUT_DIRECTION: LayoutDirection = 'LR';

const STORAGE_KEY = 'workflowBuilder.layoutDirection';

export const readLayoutDirection = (): LayoutDirection => {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'TB' ? 'TB' : DEFAULT_LAYOUT_DIRECTION;
  } catch {
    return DEFAULT_LAYOUT_DIRECTION;
  }
};

export const saveLayoutDirection = (direction: LayoutDirection) => {
  try {
    localStorage.setItem(STORAGE_KEY, direction);
  } catch {
    // Storage can be unavailable (private mode, blocked site data); the choice then lasts for this tab only
  }
};

export interface HandlePositions {
  // Incoming flow
  target: Position;
  // Outgoing flow
  source: Position;
  // Loop handles (iterator loop-out/return, loop-back), on the side perpendicular to the flow
  side: Position;
  // Offset of a loop handle along its side
  sideOffset: (percent: string) => CSSProperties;
}

const LEFT_TO_RIGHT: HandlePositions = {
  target: Position.Left,
  source: Position.Right,
  side: Position.Bottom,
  sideOffset: (percent) => ({ left: percent }),
};

const TOP_TO_BOTTOM: HandlePositions = {
  target: Position.Top,
  source: Position.Bottom,
  side: Position.Right,
  sideOffset: (percent) => ({ top: percent }),
};

export const getHandlePositions = (direction: LayoutDirection): HandlePositions =>
  direction === 'TB' ? TOP_TO_BOTTOM : LEFT_TO_RIGHT;
