import { describe, expect, it } from 'vitest';
import type { Edge, Node } from '@xyflow/react';
import { EDGE_KINDS, NODE_TYPES, getEdgeKind } from '@app/constants/workflow-builder';
import {
  applyGraphAction,
  layoutGraph,
  makeFlowEdge,
  makeRouteEdge,
  makeStartEdge,
  normalizeGraph,
  syncRouterEdges,
  type Graph,
} from './graphUtils';
import { parseYamlToGraph } from './yamlSync';

const agent = (id: string, data: Record<string, unknown> = {}): Node => ({
  id,
  type: NODE_TYPES.AGENT,
  position: { x: 0, y: 0 },
  data: { label: id, ...data },
});

const router = (id: string, routingOptions: Record<string, string>, data: Record<string, unknown> = {}): Node => ({
  id,
  type: NODE_TYPES.ROUTER,
  position: { x: 0, y: 0 },
  data: { label: id, strategy: 'smart', type: 'smart', routing_options: routingOptions, ...data },
});

const trigger = (): Node => ({
  id: 'trigger-start',
  type: NODE_TYPES.TRIGGER,
  position: { x: 0, y: 0 },
  data: { label: 'Workflow Trigger' },
});

const deepFreeze = <T>(value: T): T => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach(deepFreeze);
  }
  return value;
};

// Deep-frozen copy: any in-place write by the code under test throws (ES modules run in strict mode)
const frozenCopy = (graph: Graph): Graph => deepFreeze(structuredClone(graph));

// a -> router r -> b, c; b -> c ; b and c filter on a
const sampleGraph = (): Graph => ({
  nodes: [
    trigger(),
    agent('a'),
    agent('b', { input_filter: ['a'] }),
    agent('c', { input_filter: ['a', 'b'] }),
    router('r', { b: 'to b', c: 'to c' }),
  ],
  edges: [
    makeStartEdge('trigger-start', 'a'),
    makeFlowEdge('a', 'r'),
    makeRouteEdge('r', 'b', 'to b'),
    makeRouteEdge('r', 'c', 'to c'),
    makeFlowEdge('b', 'c'),
  ],
});

const routeEdges = (graph: Graph, routerId: string) =>
  graph.edges.filter((e) => e.source === routerId && getEdgeKind(e) === EDGE_KINDS.ROUTE);

describe('syncRouterEdges (router edge reconciliation)', () => {
  it('is idempotent: a second call on its own output returns the same graph', () => {
    const start: Graph = {
      nodes: [agent('a'), agent('b'), agent('c'), router('r', { b: 'to b', c: 'a description' })],
      edges: [],
    };
    const once = syncRouterEdges(start);
    expect(once).not.toBe(start);
    expect(
      routeEdges(once, 'r')
        .map((e) => e.target)
        .sort()
    ).toEqual(['b', 'c']);
    expect(syncRouterEdges(once)).toBe(once);
  });

  it('is idempotent with an empty-string routing_options value', () => {
    const start: Graph = {
      nodes: [agent('a'), agent('b'), agent('c'), router('r', { b: '', c: 'to c' })],
      edges: [],
    };
    const once = syncRouterEdges(start);
    expect(routeEdges(once, 'r')).toHaveLength(2);
    expect(routeEdges(once, 'r').find((e) => e.target === 'b')?.label).toBe('to b');
    expect(syncRouterEdges(once)).toBe(once);
  });

  it('returns the same graph object when edges are already in sync', () => {
    const graph = sampleGraph();
    expect(syncRouterEdges(graph)).toBe(graph);
  });

  it('removes stale and duplicate branch edges, then settles', () => {
    const graph = sampleGraph();
    graph.edges.push(makeRouteEdge('r', 'b', 'to b'));
    graph.edges.push({ ...makeRouteEdge('r', 'zzz'), id: 'e-r-zzz-stale', target: 'zzz' });
    graph.nodes = graph.nodes.map((n) =>
      n.id === 'r' ? { ...n, data: { ...n.data, routing_options: { b: 'to b' } } } : n
    );
    const once = syncRouterEdges(graph);
    expect(routeEdges(once, 'r').map((e) => e.target)).toEqual(['b']);
    expect(syncRouterEdges(once)).toBe(once);
  });

  it('ignores routing_options that point at nodes that do not exist, and settles', () => {
    const start: Graph = { nodes: [agent('a'), router('r', { missing: '', a: 'to a' })], edges: [] };
    const once = syncRouterEdges(start);
    expect(routeEdges(once, 'r').map((e) => e.target)).toEqual(['a']);
    expect(syncRouterEdges(once)).toBe(once);
  });

  it('settles on graphs parsed from YAML, with an empty-string option', () => {
    const parsed = parseYamlToGraph(`arium:
  agents:
    - name: a
    - name: b
    - name: c
  routers:
    - name: r
      type: smart
      routing_options:
        b: ""
        c: "to c"
  workflow:
    start: a
    edges:
      - from: a
        router: r
        to: [b, c]
    end: [b, c]
`);
    expect(parsed.error).toBeUndefined();
    const once = syncRouterEdges({ nodes: parsed.nodes, edges: parsed.edges });
    expect(syncRouterEdges(once)).toBe(once);
    expect(normalizeGraph(once)).toEqual(normalizeGraph(normalizeGraph(once)));
  });
});

describe('graph transforms do not mutate their input', () => {
  it('renameNode', () => {
    const graph = frozenCopy(sampleGraph());
    const before = structuredClone(graph);
    const next = applyGraphAction(graph, { type: 'renameNode', oldId: 'b', newId: 'b2' });
    expect(graph).toEqual(before);
    expect(next).not.toBe(graph);
  });

  it('renameNode of a router target and the start node', () => {
    const graph = frozenCopy(sampleGraph());
    const before = structuredClone(graph);
    applyGraphAction(graph, { type: 'renameNode', oldId: 'a', newId: 'a2' });
    applyGraphAction(graph, { type: 'renameNode', oldId: 'r', newId: 'r2' });
    expect(graph).toEqual(before);
  });

  it('deleteElements for a node', () => {
    const graph = frozenCopy(sampleGraph());
    const before = structuredClone(graph);
    const next = applyGraphAction(graph, { type: 'deleteElements', nodeIds: ['b'] });
    expect(graph).toEqual(before);
    expect(next).not.toBe(graph);
  });

  it('deleteElements for the start node and for edges', () => {
    const graph = frozenCopy(sampleGraph());
    const before = structuredClone(graph);
    applyGraphAction(graph, { type: 'deleteElements', nodeIds: ['a'] });
    applyGraphAction(graph, { type: 'deleteElements', edgeIds: ['e-r-b', 'e-b-c'] });
    expect(graph).toEqual(before);
  });

  it('syncRouterEdges and normalizeGraph', () => {
    const start: Graph = { nodes: [agent('a'), agent('b'), router('r', { a: '', b: 'x' })], edges: [] };
    const graph = frozenCopy(start);
    syncRouterEdges(graph);
    normalizeGraph(graph);
    expect(graph).toEqual(start);
  });
});

describe('rename and delete results', () => {
  it('rename rewrites references, edges and records the previous YAML name', () => {
    const next = applyGraphAction(sampleGraph(), { type: 'renameNode', oldId: 'b', newId: 'b2' });
    expect(next.nodes.map((n) => n.id)).toContain('b2');
    expect(next.nodes.map((n) => n.id)).not.toContain('b');
    expect(next.nodes.find((n) => n.id === 'b2')?.data.yamlName).toBe('b');
    expect(next.nodes.find((n) => n.id === 'c')?.data.input_filter).toEqual(['a', 'b2']);
    expect(Object.keys(next.nodes.find((n) => n.id === 'r')?.data.routing_options as object)).toEqual(['b2', 'c']);
    next.edges.forEach((e) => {
      expect(e.source).not.toBe('b');
      expect(e.target).not.toBe('b');
    });
    expect(syncRouterEdges(next)).toBe(next);
  });

  it('rename keeps yamlName at the original name across repeated renames', () => {
    const once = applyGraphAction(sampleGraph(), { type: 'renameNode', oldId: 'b', newId: 'b2' });
    const twice = applyGraphAction(once, { type: 'renameNode', oldId: 'b2', newId: 'b3' });
    expect(twice.nodes.find((n) => n.id === 'b3')?.data.yamlName).toBe('b');
  });

  it('rename to a taken or reserved name changes nothing', () => {
    const graph = sampleGraph();
    expect(applyGraphAction(graph, { type: 'renameNode', oldId: 'b', newId: 'c' })).toBe(graph);
    expect(applyGraphAction(graph, { type: 'renameNode', oldId: 'b', newId: 'end' })).toBe(graph);
  });

  it('delete leaves no reference to the node', () => {
    const next = applyGraphAction(sampleGraph(), { type: 'deleteElements', nodeIds: ['b'] });
    expect(next.nodes.map((n) => n.id)).not.toContain('b');
    expect(next.nodes.find((n) => n.id === 'c')?.data.input_filter).toEqual(['a']);
    expect(Object.keys(next.nodes.find((n) => n.id === 'r')?.data.routing_options as object)).toEqual(['c']);
    next.edges.forEach((e: Edge) => {
      expect(e.source).not.toBe('b');
      expect(e.target).not.toBe('b');
    });
  });

  it('deleting the start node hands the trigger to another step', () => {
    const next = applyGraphAction(sampleGraph(), { type: 'deleteElements', nodeIds: ['a'] });
    const start = next.edges.find((e) => getEdgeKind(e) === EDGE_KINDS.START);
    expect(start?.target).toBe('b');
    expect(next.nodes.find((n) => n.id === 'b')?.data.input_filter).toBeUndefined();
  });
});

describe('layoutGraph direction', () => {
  const chain: Graph = {
    nodes: [agent('a'), agent('b'), agent('c')],
    edges: [makeFlowEdge('a', 'b'), makeFlowEdge('b', 'c')],
  };
  const positionOf = (graph: Graph, id: string) => graph.nodes.find((n) => n.id === id)!.position;

  it('lays a chain out left to right by default', () => {
    const laidOut = layoutGraph(chain);
    expect(positionOf(laidOut, 'b').x).toBeGreaterThan(positionOf(laidOut, 'a').x);
    expect(positionOf(laidOut, 'c').x).toBeGreaterThan(positionOf(laidOut, 'b').x);
    expect(positionOf(laidOut, 'b').y).toBe(positionOf(laidOut, 'a').y);
  });

  it('lays a chain out top to bottom when asked', () => {
    const laidOut = layoutGraph(chain, 'TB');
    expect(positionOf(laidOut, 'b').y).toBeGreaterThan(positionOf(laidOut, 'a').y);
    expect(positionOf(laidOut, 'c').y).toBeGreaterThan(positionOf(laidOut, 'b').y);
    expect(positionOf(laidOut, 'b').x).toBe(positionOf(laidOut, 'a').x);
  });

  it('does not move the input nodes', () => {
    layoutGraph(chain, 'TB');
    expect(chain.nodes.every((n) => n.position.x === 0 && n.position.y === 0)).toBe(true);
  });
});
