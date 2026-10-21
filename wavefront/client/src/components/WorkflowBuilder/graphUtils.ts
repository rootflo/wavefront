import { Edge, Node } from '@xyflow/react';
import { NODE_TYPES } from '@app/constants/workflow-builder';

const ROUTER_EDGE_COLOR = '#f97316';

// Rename a node and propagate the new ID to iterator execute_node and router routing_options
export const computeNewNodes = (nds: Node[], oldId: string, newId: string): Node[] =>
  nds.map((node) => {
    if (node.id === oldId) {
      return {
        ...node,
        id: newId,
        data: {
          ...node.data,
          label: newId,
        },
      };
    }
    // If it's an iterator executing this node, update execute_node
    if (node.type === NODE_TYPES.ITERATOR && node.data?.execute_node === oldId) {
      return {
        ...node,
        data: {
          ...node.data,
          execute_node: newId,
        },
      };
    }
    // If it's a router with routing_options containing oldId, rename the branch key
    if (node.type === NODE_TYPES.ROUTER && node.data?.routing_options) {
      const opts = { ...(node.data.routing_options as Record<string, string>) };
      if (opts[oldId] !== undefined) {
        const val = opts[oldId];
        delete opts[oldId];
        opts[newId] = val;
        return {
          ...node,
          data: {
            ...node.data,
            routing_options: opts,
          },
        };
      }
    }
    return node;
  });

// Re-point edges (and their ids) from a renamed node to its new ID
export const computeNewEdges = (eds: Edge[], oldId: string, newId: string): Edge[] =>
  eds.map((edge) => {
    const updated = { ...edge };
    if (edge.source === oldId) {
      updated.source = newId;
      updated.id = edge.id.replace(oldId, newId);
    }
    if (edge.target === oldId) {
      updated.target = newId;
      updated.id = edge.id.replace(oldId, newId);
    }
    return updated;
  });

// Drop every edge connected to a deleted node
export const computeRemainingEdges = (eds: Edge[], nodeId: string): Edge[] =>
  eds.filter((e) => e.source !== nodeId && e.target !== nodeId);

// Clean up routing options in any router targeting the deleted node, and clean up iterators.
// NOTE: mutates the node data objects in place.
export const cleanupDeletedNodeReferences = (remainingNodes: Node[], nodeId: string) => {
  remainingNodes.forEach((node) => {
    if (node.type === NODE_TYPES.ROUTER && node.data?.routing_options) {
      const opts = { ...(node.data.routing_options as Record<string, string>) };
      if (opts[nodeId]) {
        delete opts[nodeId];
        node.data.routing_options = opts;
      }
    }
    if (node.type === NODE_TYPES.ITERATOR && node.data?.execute_node === nodeId) {
      node.data.execute_node = undefined;
    }
    if (node.data?.loopedBy === nodeId) {
      node.data.isLoopTarget = false;
      node.data.loopedBy = undefined;
    }
  });
};

// Reconcile orange router edges with each router's routing_options.
// NOTE: label updates are applied in place to the existing edge objects.
export const computeSyncedRouterEdges = (nodes: Node[], edges: Edge[]): { edges: Edge[]; changed: boolean } => {
  let edgesChanged = false;
  let newEdges = [...edges];
  let removedEdges = false;

  // 1. Add missing orange edges
  nodes
    .filter((n) => n.type === NODE_TYPES.ROUTER)
    .forEach((router) => {
      const routingOptions = (router.data.routing_options as Record<string, string>) || {};
      const targetIds = Object.keys(routingOptions);

      targetIds.forEach((targetId) => {
        const edgeId = `e-${router.id}-${targetId}`;
        const existingEdge = newEdges.find((e) => e.id === edgeId);

        const intentText = routingOptions[targetId] || `to ${targetId}`;
        const shortLabel = intentText.length > 25 ? intentText.substring(0, 25) + '...' : intentText;

        if (!existingEdge) {
          newEdges.push({
            id: edgeId,
            source: router.id,
            target: targetId,
            label: shortLabel,
            labelStyle: { fill: ROUTER_EDGE_COLOR, fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
            labelBgPadding: [6, 4] as [number, number],
            labelBgBorderRadius: 4,
            labelBgStyle: { fill: 'hsl(var(--background))', stroke: '#border', strokeWidth: 1 },
            style: { stroke: ROUTER_EDGE_COLOR, strokeWidth: 2 },
          });
          edgesChanged = true;
        } else if (existingEdge.label !== shortLabel) {
          existingEdge.label = shortLabel;
          edgesChanged = true;
        }
      });
    });

  // 2. Remove orphaned orange edges
  newEdges = newEdges.filter((edge) => {
    if (edge.style?.stroke === ROUTER_EDGE_COLOR) {
      const routerNode = nodes.find((n) => n.id === edge.source);
      if (routerNode && routerNode.type === NODE_TYPES.ROUTER) {
        const opts = (routerNode.data.routing_options as Record<string, string>) || {};
        if (!opts[edge.target]) {
          removedEdges = true;
          return false;
        }
      }
    }
    return true;
  });

  return { edges: newEdges, changed: edgesChanged || removedEdges };
};
