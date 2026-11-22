import { createContext, useContext } from 'react';
import { DEFAULT_LAYOUT_DIRECTION, getHandlePositions, LayoutDirection } from '../layoutDirection';

// Editor state and actions that node components need. Kept out of node data so that node objects stay stable
// between renders (React.memo on the node components only holds when `data` is unchanged).
export interface WorkflowActions {
  startNodeId: string;
  deleteNode: (nodeId: string) => void;
  layoutDirection: LayoutDirection;
}

const noop = () => {};

export const WorkflowActionsContext = createContext<WorkflowActions>({
  startNodeId: '',
  deleteNode: noop,
  layoutDirection: DEFAULT_LAYOUT_DIRECTION,
});

export const useWorkflowActions = () => useContext(WorkflowActionsContext);

// Where a node's handles sit for the current canvas direction
export const useHandlePositions = () => getHandlePositions(useWorkflowActions().layoutDirection);

export const useLayoutDirection = () => useWorkflowActions().layoutDirection;
