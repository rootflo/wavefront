import { createContext, useContext } from 'react';

// Editor state and actions that node components need. Kept out of node data so that node objects stay stable
// between renders (React.memo on the node components only holds when `data` is unchanged).
export interface WorkflowActions {
  startNodeId: string;
  deleteNode: (nodeId: string) => void;
}

const noop = () => {};

export const WorkflowActionsContext = createContext<WorkflowActions>({ startNodeId: '', deleteNode: noop });

export const useWorkflowActions = () => useContext(WorkflowActionsContext);
