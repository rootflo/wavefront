import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useNodesInitialized,
  Controls,
  Background,
  BackgroundVariant,
  Connection,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
  ReactFlowInstance,
  OnBeforeDelete,
  OnConnectEnd,
  OnDelete,
  IsValidConnection,
  XYPosition,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  AddableNodeType,
  EDGE_KINDS,
  NODE_TYPES,
  getEdgeKind,
  getNodeTypeDefinition,
} from '@app/constants/workflow-builder';
import { Sidebar } from './Sidebar';
import { PropertyPanel } from './PropertyPanel';
import { AgentNode, RouterNode, TriggerNode, FunctionNode, IteratorNode, SubworkflowNode } from './nodes';
import { parseYamlToGraph, serializeGraphToYaml } from './yamlSync';
import {
  Graph,
  GraphAction,
  LOOP_BACK_HANDLE,
  applyGraphAction,
  getRoutingOptions,
  getStartNodeId,
  isRouteEdge,
  keepPositions,
  layoutGraph,
  needsLayout,
  nextNodeId,
  nextNodePosition,
  normalizeGraph,
  settleYamlNames,
  validateConnection,
} from './graphUtils';
import { createWorkflowNode } from './nodeFactory';
import { ProblemsPanel } from './ProblemsPanel';
import { LayoutDirection, readLayoutDirection, saveLayoutDirection } from './layoutDirection';
import { ROUTED_EDGE_TYPE } from './autoLayout';
import { RoutedEdge } from './canvas/RoutedEdge';
import type { GraphIssue } from '@app/types/workflow-builder';
import { WorkflowTemplate, createLinearTemplate, createRouterTemplate } from './workflowTemplates';
import { WorkflowActions, WorkflowActionsContext } from './hooks/useWorkflowActions';
import { CanvasToolbar } from './canvas/CanvasToolbar';
import { CanvasLegend } from './canvas/CanvasLegend';
import { EmptyCanvasWelcome } from './canvas/EmptyCanvasWelcome';
import { AddNodeMenu, AddNodeMenuState } from './canvas/AddNodeMenu';
import { IntentPromptModal, IntentPromptState } from './canvas/IntentPromptModal';

// Setup custom nodes mapping
const nodeTypes = {
  [NODE_TYPES.TRIGGER]: TriggerNode,
  [NODE_TYPES.AGENT]: AgentNode,
  [NODE_TYPES.ROUTER]: RouterNode,
  [NODE_TYPES.FUNCTION]: FunctionNode,
  [NODE_TYPES.ITERATOR]: IteratorNode,
  [NODE_TYPES.SUBWORKFLOW]: SubworkflowNode,
};

const edgeTypes = { [ROUTED_EDGE_TYPE]: RoutedEdge };

// Node types accepted when dropped from the sidebar palette
const DROPPABLE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.ROUTER,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
];

const FILTER_FOCUS_COLOR = '#3b82f6';
const FIT_VIEW_OPTIONS = { padding: 0.2, duration: 400 };

// Runs the layout again once every card has been rendered and measured, so no block is placed from a guessed height
interface RelayoutOnMeasureProps {
  pending: React.MutableRefObject<boolean>;
  onMeasured: () => void;
}

const RelayoutOnMeasure = ({ pending, onMeasured }: RelayoutOnMeasureProps) => {
  const initialized = useNodesInitialized();
  useEffect(() => {
    if (!initialized || !pending.current) return;
    pending.current = false;
    onMeasured();
  }, [initialized, pending, onMeasured]);
  return null;
};

interface WorkflowVisualEditorProps {
  yamlContent?: string;
  onChange?: (newYaml: string) => void;
}

export const WorkflowVisualEditor = ({ yamlContent = '', onChange }: WorkflowVisualEditorProps) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [layoutDirection, setLayoutDirection] = useState<LayoutDirection>(readLayoutDirection);
  // Read inside callbacks/effects that shouldn't re-run when only the direction changes
  const layoutDirectionRef = useRef(layoutDirection);
  layoutDirectionRef.current = layoutDirection;
  // Only the id is stored: the selected node is always read from the current nodes
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showDataWires, setShowDataWires] = useState<boolean>(false);

  const [addNodeMenu, setAddNodeMenu] = useState<AddNodeMenuState | null>(null);
  const [intentPrompt, setIntentPrompt] = useState<IntentPromptState | null>(null);

  // Latest committed graph, so event handlers never compute from a stale render closure
  const graphRef = useRef<Graph>({ nodes, edges });
  graphRef.current = { nodes, edges };

  // Set when positions came from estimated card sizes; the next time every node is measured they are redone
  const relayoutOnMeasureRef = useRef(false);

  // The YAML the current graph corresponds to: the last YAML parsed from props or emitted by this editor.
  // null until the first parse, so the initial yamlContent is always loaded.
  const currentYamlRef = useRef<string | null>(null);

  // Why the YAML cannot be drawn (syntax error, no `arium` key). While set the canvas is empty and read-only,
  // so edits can never overwrite the user's YAML.
  const [yamlError, setYamlError] = useState<string | null>(null);
  const yamlErrorRef = useRef<string | null>(null);
  // Problems in the drawn graph that will make the saved workflow fail or run differently
  const [issues, setIssues] = useState<GraphIssue[]>([]);
  // Dismissing hides the current warnings; a new set (after the next edit) shows again
  const [issuesDismissed, setIssuesDismissed] = useState(false);

  const reportYamlError = useCallback((error: string | null) => {
    yamlErrorRef.current = error;
    setYamlError(error);
  }, []);

  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) ?? null, [nodes, selectedNodeId]);

  const startNodeId = useMemo(() => getStartNodeId({ nodes, edges }), [nodes, edges]);

  // Filter edges for clean, prettified pipeline visualization
  // Non-execution memory filter edges are hidden by default unless toggled on or when a node is actively selected
  const visibleEdges = useMemo(() => {
    const touchesSelection = (e: Edge) =>
      !!selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId);
    return edges
      .filter((e) => getEdgeKind(e) !== EDGE_KINDS.FILTER || showDataWires || touchesSelection(e))
      .map((e) => {
        if (getEdgeKind(e) === EDGE_KINDS.FILTER && touchesSelection(e)) {
          return {
            ...e,
            animated: true,
            style: { ...e.style, stroke: FILTER_FOCUS_COLOR, strokeWidth: 2, opacity: 1 },
          };
        }
        return e;
      });
  }, [edges, showDataWires, selectedNodeId]);

  // Sync YAML -> Graph, only for YAML that did not come from this editor
  useEffect(() => {
    if (yamlContent === currentYamlRef.current) return;
    currentYamlRef.current = yamlContent;
    const result = parseYamlToGraph(yamlContent);
    reportYamlError(result.error ?? null);
    setIssues([]);
    const parsed = normalizeGraph(result);
    // A graph that shares no node with the canvas is a fresh load: lay it out in the chosen direction
    const previous = graphRef.current.nodes;
    const isFreshLoad = !parsed.nodes.some((n) => previous.some((p) => p.id === n.id));
    const next =
      needsLayout(parsed) || isFreshLoad
        ? layoutGraph(parsed, layoutDirectionRef.current)
        : keepPositions(parsed, previous);
    // Real card heights are only known once rendered: lay out again from them
    relayoutOnMeasureRef.current = isFreshLoad && next.nodes.length > 0;
    graphRef.current = next;
    setNodes(next.nodes);
    setEdges(next.edges);
  }, [yamlContent, setNodes, setEdges, reportYamlError]);

  // Commit a new graph: the single place where canvas state is written and YAML is derived from it.
  // Returns false (and changes nothing) when the YAML cannot be written.
  const commitGraph = useCallback(
    (graph: Graph): boolean => {
      let next = graph;
      const emit = onChangeRef.current;
      if (emit) {
        const result = serializeGraphToYaml(next.nodes, next.edges, currentYamlRef.current ?? '');
        if (!result.ok) {
          reportYamlError(result.error);
          return false;
        }
        currentYamlRef.current = result.yaml;
        setIssues(result.issues);
        setIssuesDismissed(false);
        emit(result.yaml);
        // Every node's config is now stored under its current id
        next = settleYamlNames(next);
      }
      graphRef.current = next;
      setNodes(next.nodes);
      setEdges(next.edges);
      return true;
    },
    [setNodes, setEdges, reportYamlError]
  );

  // Apply one editor action to the latest graph. Returns whether anything changed.
  const dispatch = useCallback(
    (action: GraphAction): boolean => {
      if (yamlErrorRef.current) return false;
      const prev = graphRef.current;
      const next = applyGraphAction(prev, action);
      if (next === prev) return false;
      return commitGraph(next);
    },
    [commitGraph]
  );

  const fitViewSoon = useCallback(() => {
    if (!reactFlowInstance) return;
    setTimeout(() => reactFlowInstance.fitView(FIT_VIEW_OPTIONS), 50);
  }, [reactFlowInstance]);

  // Merge a partial data patch into a node
  const onUpdateNode = useCallback(
    (id: string, patch: Record<string, unknown>) => {
      dispatch({ type: 'updateNodeData', id, patch });
    },
    [dispatch]
  );

  // Rename a node and every reference to it (edges, routing_options, execute_node, input_filter, flow_pattern, start)
  const onRenameNode = useCallback(
    (oldId: string, newId: string) => {
      if (dispatch({ type: 'renameNode', oldId, newId })) {
        setSelectedNodeId((current) => (current === oldId ? newId : current));
      }
    },
    [dispatch]
  );

  // Delete a node, its edges and every reference to it
  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      dispatch({ type: 'deleteElements', nodeIds: [nodeId] });
    },
    [dispatch]
  );

  // Add a node and select it. connectFrom wires it to an existing step in the same commit.
  const insertNode = useCallback(
    (newNode: Node, connectFrom?: { source: string; sourceHandle?: string | null }) => {
      if (!dispatch({ type: 'addNode', node: newNode, connectFrom })) return false;
      setSelectedNodeId(newNode.id);
      return true;
    },
    [dispatch]
  );

  const buildNode = useCallback((type: AddableNodeType, position?: XYPosition) => {
    const current = graphRef.current.nodes;
    const prefix = getNodeTypeDefinition(type)?.prefix ?? 'step';
    return createWorkflowNode(type, nextNodeId(prefix, current), position ?? nextNodePosition(current));
  }, []);

  // Toolbar / sidebar add: place the step to the right of the right-most one and keep every other position
  const handleAddNode = useCallback(
    (type: AddableNodeType) => {
      if (insertNode(buildNode(type))) fitViewSoon();
    },
    [buildNode, insertNode, fitViewSoon]
  );

  const handleAddAgent = useCallback(() => handleAddNode(NODE_TYPES.AGENT), [handleAddNode]);
  const handleAddRouter = useCallback(() => handleAddNode(NODE_TYPES.ROUTER), [handleAddNode]);
  const handleAddFunction = useCallback(() => handleAddNode(NODE_TYPES.FUNCTION), [handleAddNode]);
  const handleAddIterator = useCallback(() => handleAddNode(NODE_TYPES.ITERATOR), [handleAddNode]);
  const handleAddSubworkflow = useCallback(() => handleAddNode(NODE_TYPES.SUBWORKFLOW), [handleAddNode]);

  // Set the workflow entry step
  const handleSetStartAgent = useCallback(
    (nodeId: string) => {
      dispatch({ type: 'setStart', nodeId });
    },
    [dispatch]
  );

  // Explicit Auto-Layout: positions are canvas-only, so no YAML is emitted
  const handleAutoLayout = useCallback(() => {
    const next = layoutGraph(graphRef.current, layoutDirectionRef.current);
    graphRef.current = next;
    setNodes(next.nodes);
    setEdges(next.edges);
    fitViewSoon();
  }, [setNodes, setEdges, fitViewSoon]);

  // Switching direction moves every node's handles, so re-run the layout in the new direction
  const handleLayoutDirectionChange = useCallback(
    (direction: LayoutDirection) => {
      if (direction === layoutDirectionRef.current) return;
      layoutDirectionRef.current = direction;
      setLayoutDirection(direction);
      saveLayoutDirection(direction);
      handleAutoLayout();
    },
    [handleAutoLayout]
  );

  // Node components read delete and start state from context, so node data stays free of callbacks
  const workflowActions = useMemo<WorkflowActions>(
    () => ({ startNodeId, deleteNode: handleDeleteNode, layoutDirection }),
    [startNodeId, handleDeleteNode, layoutDirection]
  );

  // Deletions are applied by the graph reducer (reference cleanup + YAML), never by React Flow's own remove changes
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => onNodesChange(changes.filter((c) => c.type !== 'remove')),
    [onNodesChange]
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => onEdgesChange(changes.filter((c) => c.type !== 'remove')),
    [onEdgesChange]
  );

  // Keyboard deletion: the trigger is owned by the editor and is never deleted
  const onBeforeDelete: OnBeforeDelete = useCallback(
    async ({ nodes: toDelete, edges: edgesToDelete }) => ({
      nodes: toDelete.filter((n) => n.type !== NODE_TYPES.TRIGGER),
      edges: edgesToDelete,
    }),
    []
  );

  const onDelete: OnDelete = useCallback(
    ({ nodes: deleted, edges: deletedEdges }) => {
      dispatch({
        type: 'deleteElements',
        nodeIds: deleted.map((n) => n.id),
        edgeIds: deletedEdges.map((e) => e.id),
      });
    },
    [dispatch]
  );

  const isValidConnection: IsValidConnection = useCallback(
    (connection) => validateConnection(connection, graphRef.current),
    []
  );

  const openIntentPrompt = useCallback((routerId: string, targetId: string) => {
    const router = graphRef.current.nodes.find((n) => n.id === routerId);
    setIntentPrompt({
      sourceId: routerId,
      targetId,
      currentText: router ? (getRoutingOptions(router)[targetId] ?? '') : '',
    });
  }, []);

  // Connection handler
  const onConnect = useCallback(
    (connection: Connection) => {
      const sourceNode = graphRef.current.nodes.find((n) => n.id === connection.source);
      if (dispatch({ type: 'connect', connection }) && sourceNode?.type === NODE_TYPES.ROUTER) {
        setIntentPrompt({ sourceId: connection.source, targetId: connection.target, currentText: '' });
      }
    },
    [dispatch]
  );

  // Dragging an output handle into empty canvas offers to create the next step there
  const onConnectEnd: OnConnectEnd = useCallback((event, connectionState) => {
    const { fromNode, fromHandle } = connectionState;
    if (connectionState.isValid !== null || connectionState.toNode || !fromNode) return;
    if (fromHandle?.type !== 'source' || fromHandle.id === LOOP_BACK_HANDLE) return;
    const clientX = 'clientX' in event ? event.clientX : (event.changedTouches[0]?.clientX ?? 0);
    const clientY = 'clientY' in event ? event.clientY : (event.changedTouches[0]?.clientY ?? 0);
    setAddNodeMenu({ x: clientX, y: clientY, sourceId: fromNode.id, sourceHandle: fromHandle.id });
  }, []);

  const handleQuickAdd = (type: AddableNodeType) => {
    if (!addNodeMenu || !reactFlowInstance) return;
    const { sourceId, sourceHandle } = addNodeMenu;
    setAddNodeMenu(null);
    const position = reactFlowInstance.screenToFlowPosition({ x: addNodeMenu.x, y: addNodeMenu.y });
    const newNode = buildNode(type, position);
    if (!insertNode(newNode, { source: sourceId, sourceHandle })) return;

    // Ask for the branch condition when the new step became a router branch
    const router = graphRef.current.nodes.find((n) => n.id === sourceId);
    const isBranch =
      router?.type === NODE_TYPES.ROUTER && Object.prototype.hasOwnProperty.call(getRoutingOptions(router), newNode.id);
    if (isBranch) openIntentPrompt(sourceId, newNode.id);
  };

  const handleIntentSave = () => {
    if (!intentPrompt) return;
    dispatch({
      type: 'setRouteCondition',
      routerId: intentPrompt.sourceId,
      targetId: intentPrompt.targetId,
      condition: intentPrompt.currentText || `Route to ${intentPrompt.targetId}`,
    });
    setIntentPrompt(null);
  };

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      const sourceNode = graphRef.current.nodes.find((n) => n.id === edge.source);
      if (isRouteEdge(edge, sourceNode)) openIntentPrompt(edge.source, edge.target);
    },
    [openIntentPrompt]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.type === NODE_TYPES.TRIGGER ? null : node.id);
  }, []);

  const onPaneClick = useCallback(() => setSelectedNodeId(null), []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  // Dropped steps land where they were dropped; nothing else moves
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!reactFlowInstance) return;

      const type = event.dataTransfer.getData('application/reactflow');
      if (!type || !DROPPABLE_NODE_TYPES.includes(type)) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      insertNode(buildNode(type as AddableNodeType, position));
    },
    [reactFlowInstance, buildNode, insertNode]
  );

  // Replace the canvas with a quick-start template
  const loadTemplate = useCallback(
    (template: WorkflowTemplate) => {
      if (yamlErrorRef.current) return;
      setSelectedNodeId(null);
      relayoutOnMeasureRef.current = true;
      commitGraph(layoutGraph(normalizeGraph(template), layoutDirectionRef.current));
      fitViewSoon();
    },
    [commitGraph, fitViewSoon]
  );

  // Template loader: Linear
  const handleLoadLinearTemplate = useCallback(() => loadTemplate(createLinearTemplate()), [loadTemplate]);

  // Template loader: Router
  const handleLoadRouterTemplate = useCallback(() => loadTemplate(createRouterTemplate()), [loadTemplate]);

  const handleSelectFromOutline = useCallback(
    (nodeId: string) => {
      const found = graphRef.current.nodes.find((n) => n.id === nodeId);
      if (!found) return;
      setSelectedNodeId(found.type === NODE_TYPES.TRIGGER ? null : found.id);
      reactFlowInstance?.setCenter(found.position.x + 140, found.position.y + 70, { zoom: 1, duration: 400 });
    },
    [reactFlowInstance]
  );

  return (
    <WorkflowActionsContext.Provider value={workflowActions}>
      <div className="border-border bg-background relative flex h-full w-full overflow-hidden rounded-lg border">
        <ReactFlowProvider>
          {/* ACTIVE WORKFLOW PALETTE & OUTLINE SIDEBAR */}
          <Sidebar
            nodes={nodes}
            selectedNodeId={selectedNodeId ?? undefined}
            startAgentName={startNodeId}
            onSelectNode={handleSelectFromOutline}
            onDeleteNode={handleDeleteNode}
            onAddAgent={handleAddAgent}
            onAddRouter={handleAddRouter}
            onAddFunction={handleAddFunction}
            onAddIterator={handleAddIterator}
            onAddSubworkflow={handleAddSubworkflow}
            onSetStartAgent={handleSetStartAgent}
          />

          {/* MAIN CANVAS */}
          <div className="relative h-full flex-1" ref={reactFlowWrapper}>
            {/* FLOATING ACTION TOOLBAR AT TOP */}
            <CanvasToolbar
              nodes={nodes}
              startAgentName={startNodeId}
              showDataWires={showDataWires}
              onAddAgent={handleAddAgent}
              onAddRouter={handleAddRouter}
              onAddFunction={handleAddFunction}
              onAddIterator={handleAddIterator}
              onAddSubworkflow={handleAddSubworkflow}
              onAutoLayout={handleAutoLayout}
              layoutDirection={layoutDirection}
              onLayoutDirectionChange={handleLayoutDirectionChange}
              onToggleDataWires={() => setShowDataWires((prev) => !prev)}
              onFitView={() => reactFlowInstance?.fitView({ padding: 0.2, duration: 300 })}
            />

            <ReactFlow
              // Remount on direction change so React Flow re-measures the moved handles
              key={layoutDirection}
              nodes={nodes}
              edges={visibleEdges}
              onlyRenderVisibleElements={true}
              maxZoom={2}
              defaultEdgeOptions={{
                type: 'smoothstep',
              }}
              onNodesChange={handleNodesChange}
              onEdgesChange={handleEdgesChange}
              onBeforeDelete={onBeforeDelete}
              onDelete={onDelete}
              isValidConnection={isValidConnection}
              onConnect={onConnect}
              onConnectEnd={onConnectEnd}
              onInit={setReactFlowInstance}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              onEdgeClick={onEdgeClick}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              minZoom={0.1}
              fitView
              className="bg-transparent"
            >
              <Background color="hsl(var(--border))" gap={20} size={1} variant={BackgroundVariant.Dots} />
              <RelayoutOnMeasure pending={relayoutOnMeasureRef} onMeasured={handleAutoLayout} />
              <Controls className="bg-card border-border fill-foreground" />

              {/* CANVAS LEGEND */}
              <CanvasLegend showDataWires={showDataWires} />
            </ReactFlow>

            {/* EMPTY CANVAS WELCOME & QUICK TEMPLATES */}
            {nodes.length === 0 && !yamlError && (
              <EmptyCanvasWelcome
                onLoadLinearTemplate={handleLoadLinearTemplate}
                onLoadRouterTemplate={handleLoadRouterTemplate}
                onAddAgent={handleAddAgent}
              />
            )}

            {/* YAML THAT CANNOT BE DRAWN: the canvas stays read-only so the YAML is never overwritten */}
            {yamlError && (
              <div
                role="alert"
                className="border-destructive/30 bg-card text-destructive absolute top-16 left-1/2 z-10 max-w-lg -translate-x-1/2 rounded-lg border px-4 py-3 text-xs shadow-lg"
              >
                <p className="font-semibold">The YAML cannot be shown in the visual builder</p>
                <p className="mt-1 break-words">{yamlError}</p>
                <p className="text-muted-foreground mt-1">Fix it in the YAML tab, then come back.</p>
              </div>
            )}

            {/* PROBLEMS THAT WILL BREAK THE SAVED WORKFLOW */}
            {!yamlError && !issuesDismissed && (
              <ProblemsPanel
                tone="warning"
                title={`${issues.length} ${issues.length === 1 ? 'problem' : 'problems'} in this workflow`}
                problems={issues.map((issue) => ({ message: issue.message }))}
                maxVisible={5}
                onDismiss={() => setIssuesDismissed(true)}
                className="absolute right-4 bottom-4 z-10"
              />
            )}

            {/* QUICK ADD POPUP (ON DRAGGING EDGE INTO EMPTY CANVAS) */}
            {addNodeMenu && <AddNodeMenu menu={addNodeMenu} onQuickAdd={handleQuickAdd} />}

            {/* INTENT PROMPT MODAL (ON CONNECTING ROUTER TO AGENT OR CLICKING ROUTE EDGE) */}
            {intentPrompt && (
              <IntentPromptModal
                intentPrompt={intentPrompt}
                nodes={nodes}
                onChange={setIntentPrompt}
                onSave={handleIntentSave}
                onSkip={() => setIntentPrompt(null)}
              />
            )}
          </div>

          {/* RIGHT-HAND PROPERTY INSPECTOR */}
          <PropertyPanel
            selectedNode={selectedNode}
            onClose={onPaneClick}
            onUpdateNode={onUpdateNode}
            onRenameNode={onRenameNode}
            nodes={nodes}
            startNodeId={startNodeId}
            onSetStartAgent={handleSetStartAgent}
            onDeleteNode={handleDeleteNode}
          />
        </ReactFlowProvider>
      </div>
    </WorkflowActionsContext.Provider>
  );
};
