import { Dispatch, SetStateAction, useEffect } from 'react';
import { Edge, Node } from '@xyflow/react';
import { computeSyncedRouterEdges } from '../graphUtils';

// Auto-sync visual edges when routing_options change via Property Panel
export const useSyncRouterEdges = (
  nodes: Node[],
  edges: Edge[],
  setEdges: Dispatch<SetStateAction<Edge[]>>,
  updateYaml: (newNodes: Node[], newEdges: Edge[]) => void
) => {
  useEffect(() => {
    const synced = computeSyncedRouterEdges(nodes, edges);
    if (synced.changed) {
      setEdges(synced.edges);
      updateYaml(nodes, synced.edges);
    }
  }, [nodes, edges, setEdges, updateYaml]);
};
