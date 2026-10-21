import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  BackgroundVariant,
  Connection,
  Edge,
  Node,
  ReactFlowInstance,
  OnConnectEnd,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { AddableNodeType, NODE_TYPES, getNodeTypeDefinition } from '@app/constants/workflow-builder';
import { Sidebar } from './Sidebar';
import { PropertyPanel } from './PropertyPanel';
import { AgentNode, RouterNode, TriggerNode, FunctionNode, IteratorNode, SubworkflowNode } from './nodes';
import { parseYamlToGraph, serializeGraphToYaml, getLayoutedElements, createIteratorLoopEdges } from './yamlSync';
import { cleanupDeletedNodeReferences, computeNewEdges, computeNewNodes, computeRemainingEdges } from './graphUtils';
import { createWorkflowNode } from './nodeFactory';
import { WorkflowTemplate, createLinearTemplate, createRouterTemplate } from './workflowTemplates';
import { useSyncRouterEdges } from './hooks/useSyncRouterEdges';
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

// Node types accepted when dropped from the sidebar palette
const DROPPABLE_NODE_TYPES: string[] = [
  NODE_TYPES.AGENT,
  NODE_TYPES.ROUTER,
  NODE_TYPES.FUNCTION,
  NODE_TYPES.ITERATOR,
  NODE_TYPES.SUBWORKFLOW,
];

interface WorkflowVisualEditorProps {
  yamlContent?: string;
  onChange?: (newYaml: string) => void;
}

const nextUniqueId = (prefix: string, existing: Node[]) => {
  const ids = new Set(existing.map((n) => n.id));
  let i = 1;
  while (ids.has(`${prefix}_${i}`)) i++;
  return `${prefix}_${i}`;
};

export const WorkflowVisualEditor = ({ yamlContent = '', onChange }: WorkflowVisualEditorProps) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [showDataWires, setShowDataWires] = useState<boolean>(false);

  const [addNodeMenu, setAddNodeMenu] = useState<AddNodeMenuState | null>(null);
  const [intentPrompt, setIntentPrompt] = useState<IntentPromptState | null>(null);

  // Filter edges for clean, prettified pipeline visualization
  // Non-execution memory filter edges are hidden by default unless toggled on or when a node is actively selected
  const visibleEdges = useMemo(() => {
    return edges
      .filter((e) => {
        if (!e.id.startsWith('e-filter-')) return true;
        if (showDataWires) return true;
        // Focus mode: show filter wires connected to currently selected node
        if (selectedNode && (e.source === selectedNode.id || e.target === selectedNode.id)) {
          return true;
        }
        return false;
      })
      .map((e) => {
        if (
          e.id.startsWith('e-filter-') &&
          selectedNode &&
          (e.source === selectedNode.id || e.target === selectedNode.id)
        ) {
          return {
            ...e,
            animated: true,
            style: { ...e.style, stroke: '#3b82f6', strokeWidth: 2, opacity: 1 },
          };
        }
        return e;
      });
  }, [edges, showDataWires, selectedNode]);

  // Track if we are currently parsing to prevent infinite loops
  const isParsing = useRef(false);

  // Sync Yaml -> Graph
  useEffect(() => {
    if (!isParsing.current && yamlContent) {
      const graph = parseYamlToGraph(yamlContent);
      setNodes(graph.nodes);
      setEdges(graph.edges);
    }
  }, [yamlContent, setNodes, setEdges]);

  // Sync Graph -> Yaml
  const updateYaml = useCallback(
    (newNodes: Node[], newEdges: Edge[]) => {
      if (!onChange) return;
      isParsing.current = true;
      const newYaml = serializeGraphToYaml(newNodes, newEdges, yamlContent);
      onChange(newYaml);
      setTimeout(() => {
        isParsing.current = false;
      }, 100);
    },
    [onChange, yamlContent]
  );

  // Find start agent name
  const startAgentName = useMemo(() => {
    const startEdge = edges.find((e) => e.source === 'trigger-start');
    if (startEdge) return startEdge.target;
    const firstAgent = nodes.find((n) => n.type === NODE_TYPES.AGENT);
    return firstAgent?.id || '';
  }, [edges, nodes]);

  // Update a single node's data
  const onUpdateNode = useCallback(
    (id: string, data: Record<string, unknown>) => {
      setNodes((nds) => {
        const targetNode = nds.find((n) => n.id === id);
        const isIterator = targetNode?.type === NODE_TYPES.ITERATOR;
        const oldExecuteNode = isIterator ? (targetNode.data?.execute_node as string) : undefined;
        const newExecuteNode = isIterator ? (data.execute_node as string) : undefined;

        let updatedNodes = nds.map((node) => {
          if (node.id === id) {
            const updated = { ...node, data };
            if (selectedNode?.id === id) {
              setSelectedNode(updated);
            }
            return updated;
          }
          return node;
        });

        // If iterator execute_node changed, update target node flags and loop edges
        if (isIterator && oldExecuteNode !== newExecuteNode) {
          updatedNodes = updatedNodes.map((node) => {
            if (oldExecuteNode && node.id === oldExecuteNode) {
              const stillLooped = updatedNodes.some(
                (other) =>
                  other.id !== id && other.type === NODE_TYPES.ITERATOR && other.data?.execute_node === oldExecuteNode
              );
              if (!stillLooped) {
                return { ...node, data: { ...node.data, isLoopTarget: false, loopedBy: undefined } };
              }
            }
            if (newExecuteNode && node.id === newExecuteNode) {
              return { ...node, data: { ...node.data, isLoopTarget: true, loopedBy: id } };
            }
            return node;
          });

          setEdges((eds) => {
            const filteredEdges = eds.filter(
              (e) =>
                !(
                  e.id.startsWith(`e-loop-exec-${id}-`) ||
                  (e.id.endsWith(`-${id}`) && e.id.startsWith('e-loop-return-'))
                )
            );
            const loopEdges = newExecuteNode ? createIteratorLoopEdges(id, newExecuteNode) : [];
            const newEdges = [...filteredEdges, ...loopEdges];
            updateYaml(updatedNodes, newEdges);
            return newEdges;
          });
        } else {
          updateYaml(updatedNodes, edges);
        }

        return updatedNodes;
      });
    },
    [selectedNode, setNodes, setEdges, updateYaml, edges]
  );

  // Rename a node and propagate new ID across edges and router routing_options
  const onRenameNode = useCallback(
    (oldId: string, newId: string) => {
      setNodes((nds) => {
        const newNodes = computeNewNodes(nds, oldId, newId);

        setEdges((eds) => {
          const newEdges = computeNewEdges(eds, oldId, newId);

          updateYaml(newNodes, newEdges);
          return newEdges;
        });

        const updatedSelected = newNodes.find((n) => n.id === newId);
        if (updatedSelected) {
          setSelectedNode(updatedSelected);
        }

        return newNodes;
      });
    },
    [setNodes, setEdges, updateYaml]
  );

  // Delete a node and all connected edges
  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => {
        const remainingNodes = nds.filter((n) => n.id !== nodeId);

        setEdges((eds) => {
          const remainingEdges = computeRemainingEdges(eds, nodeId);
          cleanupDeletedNodeReferences(remainingNodes, nodeId);

          updateYaml(remainingNodes, remainingEdges);
          return remainingEdges;
        });

        return remainingNodes;
      });

      if (selectedNode?.id === nodeId) {
        setSelectedNode(null);
      }
    },
    [selectedNode, setNodes, setEdges, updateYaml]
  );

  // Generic helper to insert any node type with horizontal auto-layout
  const insertNode = useCallback(
    (newNode: Node, isFirstNode = false) => {
      const newNodes = [...nodes, newNode];
      const newEdges = [...edges];

      if (isFirstNode) {
        const triggerNode: Node = {
          id: 'trigger-start',
          type: NODE_TYPES.TRIGGER,
          position: { x: newNode.position.x - 360, y: newNode.position.y },
          data: {
            label: 'Workflow Trigger',
            description: 'Triggers the execution and hands off input to the entry agent.',
            type: 'trigger',
          },
        };
        newNodes.unshift(triggerNode);
        newEdges.push({
          id: `e-start-${newNode.id}`,
          source: 'trigger-start',
          target: newNode.id,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#a855f7', strokeWidth: 2 },
        });
      }

      const layouted = getLayoutedElements(newNodes, newEdges, 'LR');
      setNodes(layouted.nodes);
      setEdges(layouted.edges);
      updateYaml(layouted.nodes, layouted.edges);
      const created = layouted.nodes.find((n) => n.id === newNode.id);
      setSelectedNode(created || newNode);
      if (reactFlowInstance) {
        setTimeout(() => {
          reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
        }, 50);
      }
    },
    [nodes, edges, reactFlowInstance, setNodes, setEdges, updateYaml]
  );

  // Add an Agent
  const handleAddAgent = useCallback(() => {
    const newId = nextUniqueId('agent', nodes);
    const isFirstAgent = nodes.filter((n) => n.type === NODE_TYPES.AGENT).length === 0;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 250, y: 150 };

    insertNode(
      {
        id: newId,
        type: NODE_TYPES.AGENT,
        position,
        data: {
          label: newId,
          role: 'General Assistant',
          job: 'Assists with tasks and processes incoming workflow input.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.7,
          isStartNode: isFirstAgent,
          type: 'agent',
        },
      },
      isFirstAgent
    );
  }, [nodes, insertNode]);

  // Add a Router
  const handleAddRouter = useCallback(() => {
    const newId = nextUniqueId('router', nodes);

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: NODE_TYPES.ROUTER,
      position,
      data: {
        label: newId,
        strategy: 'smart',
        provider: 'openai',
        model: 'gpt-4o-mini',
        temperature: 0.3,
        context_description: 'Evaluates requests and directs to the most suitable step.',
        fallback_strategy: 'first',
        routing_options: {},
        type: 'router',
      },
    });
  }, [nodes, insertNode]);

  // Add a Function Node
  const handleAddFunction = useCallback(() => {
    const newId = nextUniqueId('function', nodes);

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: NODE_TYPES.FUNCTION,
      position,
      data: {
        label: newId,
        function_name: 'passthrough',
        description: 'Executes deterministic data transformation.',
        type: 'function',
      },
    });
  }, [nodes, insertNode]);

  // Add an Iterator Node
  const handleAddIterator = useCallback(() => {
    const newId = nextUniqueId('iterator', nodes);

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: NODE_TYPES.ITERATOR,
      position,
      data: {
        label: newId,
        execute_node: '',
        forward_all_results: false,
        type: 'iterator',
      },
    });
  }, [nodes, insertNode]);

  // Add a Sub-Workflow Node
  const handleAddSubworkflow = useCallback(() => {
    const newId = nextUniqueId('subworkflow', nodes);

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: NODE_TYPES.SUBWORKFLOW,
      position,
      data: {
        label: newId,
        yaml_file: '',
        inherit_variables: true,
        type: 'subworkflow',
      },
    });
  }, [nodes, insertNode]);

  // Set Start Agent
  const handleSetStartAgent = useCallback(
    (agentId: string) => {
      setNodes((nds) => {
        const updatedNodes = nds.map((n) => ({
          ...n,
          data: {
            ...n.data,
            isStartNode: n.id === agentId,
          },
        }));

        setEdges((eds) => {
          const filtered = eds.filter((e) => e.source !== 'trigger-start');
          filtered.unshift({
            id: `e-start-${agentId}`,
            source: 'trigger-start',
            target: agentId,
            animated: true,
            style: { stroke: '#a855f7', strokeWidth: 2 },
          });

          const layouted = getLayoutedElements(updatedNodes, filtered, 'LR');
          updateYaml(layouted.nodes, layouted.edges);
          return layouted.edges;
        });

        return updatedNodes;
      });
    },
    [setNodes, setEdges, updateYaml]
  );

  // Re-run Auto-Layout
  const handleAutoLayout = useCallback(() => {
    const layouted = getLayoutedElements(nodes, edges, 'LR');
    setNodes([...layouted.nodes]);
    setEdges([...layouted.edges]);
    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
      }, 50);
    }
  }, [nodes, edges, reactFlowInstance, setNodes, setEdges]);

  // Attach delete handlers to nodes
  const nodesWithHandlers = useMemo(() => {
    return nodes.map((n) => ({
      ...n,
      data: {
        ...n.data,
        isStartNode: n.id === startAgentName,
        onDelete: () => handleDeleteNode(n.id),
      },
    }));
  }, [nodes, startAgentName, handleDeleteNode]);

  // Auto-sync visual edges when routing_options change via Property Panel
  useSyncRouterEdges(nodes, edges, setEdges, updateYaml);

  // Connection handler
  const onConnect = useCallback(
    (params: Connection | Edge) => {
      const sourceNode = nodes.find((n) => n.id === params.source);
      const isRouter = sourceNode?.type === NODE_TYPES.ROUTER;
      const isIteratorLoop = sourceNode?.type === NODE_TYPES.ITERATOR && params.sourceHandle === 'loop-out';

      if (isIteratorLoop && params.source && params.target) {
        const iteratorId = params.source;
        const targetId = params.target;
        setNodes((nds) => {
          const updatedNodes = nds.map((node) => {
            if (node.id === iteratorId) {
              return { ...node, data: { ...node.data, execute_node: targetId } };
            }
            if (node.id === targetId) {
              return { ...node, data: { ...node.data, isLoopTarget: true, loopedBy: iteratorId } };
            }
            return node;
          });
          setEdges((eds) => {
            const filteredEdges = eds.filter(
              (e) =>
                !(
                  e.id.startsWith(`e-loop-exec-${iteratorId}-`) ||
                  (e.id.endsWith(`-${iteratorId}`) && e.id.startsWith('e-loop-return-'))
                )
            );
            const loopEdges = createIteratorLoopEdges(iteratorId, targetId);
            const newEdges = [...filteredEdges, ...loopEdges];
            updateYaml(updatedNodes, newEdges);
            return newEdges;
          });
          return updatedNodes;
        });
        return;
      }

      const isFromIterator = sourceNode?.type === NODE_TYPES.ITERATOR;

      let currentNodes = nodes;
      if (isRouter && params.source && params.target) {
        currentNodes = nodes.map((n) => {
          if (n.id === params.source) {
            const opts = (n.data.routing_options as Record<string, string>) || {};
            return {
              ...n,
              data: { ...n.data, routing_options: { ...opts, [params.target!]: `Route to ${params.target}` } },
            };
          }
          return n;
        });
        setNodes(currentNodes);
      }

      setEdges((eds) => {
        const newEdges = addEdge(
          {
            ...params,
            type: 'smoothstep',
            style: {
              stroke: isRouter ? '#f97316' : isFromIterator ? '#6366f1' : '#64748b',
              strokeWidth: 2,
            },
            animated: true,
            label: isFromIterator ? 'On Complete [All]' : undefined,
            labelStyle: isFromIterator ? { fill: '#6366f1', fontSize: 9, fontWeight: 600 } : undefined,
            labelBgStyle: isFromIterator ? { fill: 'hsl(var(--card))', stroke: '#6366f1', strokeWidth: 1 } : undefined,
            labelBgPadding: isFromIterator ? ([6, 3] as [number, number]) : undefined,
            labelBgBorderRadius: isFromIterator ? 4 : undefined,
          } as unknown as Edge,
          eds
        );
        updateYaml(currentNodes, newEdges);
        return newEdges;
      });

      if (isRouter && params.source && params.target) {
        setIntentPrompt({
          sourceId: params.source,
          targetId: params.target,
          currentText: '',
        });
      }
    },
    [nodes, setNodes, setEdges, updateYaml]
  );

  const onConnectEnd: OnConnectEnd = useCallback((event, connectionState) => {
    if (!connectionState.isValid && connectionState.fromNode) {
      const clientX = 'clientX' in event ? event.clientX : (event.touches[0]?.clientX ?? 0);
      const clientY = 'clientY' in event ? event.clientY : (event.touches[0]?.clientY ?? 0);
      setAddNodeMenu({ x: clientX, y: clientY, sourceId: connectionState.fromNode.id });
    }
  }, []);

  const handleQuickAdd = (type: AddableNodeType) => {
    if (!addNodeMenu || !reactFlowInstance) return;
    const position = reactFlowInstance.screenToFlowPosition({ x: addNodeMenu.x, y: addNodeMenu.y });

    const prefix = getNodeTypeDefinition(type)?.prefix ?? 'step';
    const newNodeId = nextUniqueId(prefix, nodes);

    const newNode = createWorkflowNode(type, newNodeId, position);

    const newEdge: Edge = {
      id: `e-${addNodeMenu.sourceId}-${newNodeId}`,
      source: addNodeMenu.sourceId,
      target: newNodeId,
      type: 'smoothstep',
      style: {
        stroke: nodes.find((n) => n.id === addNodeMenu.sourceId)?.type === NODE_TYPES.ROUTER ? '#f97316' : '#64748b',
        strokeWidth: 2,
      },
    };

    let currentNodes = [...nodes, newNode];
    const sourceNode = nodes.find((n) => n.id === addNodeMenu.sourceId);
    if (sourceNode?.type === NODE_TYPES.ROUTER) {
      currentNodes = currentNodes.map((n) => {
        if (n.id === addNodeMenu.sourceId) {
          const opts = (n.data.routing_options as Record<string, string>) || {};
          return {
            ...n,
            data: { ...n.data, routing_options: { ...opts, [newNodeId]: `Route to ${newNodeId}` } },
          };
        }
        return n;
      });
    }

    const newEdges = [...edges, newEdge];
    const layouted = getLayoutedElements(currentNodes, newEdges, 'LR');
    setNodes(layouted.nodes);
    setEdges(layouted.edges);
    updateYaml(layouted.nodes, layouted.edges);
    setAddNodeMenu(null);
    const created = layouted.nodes.find((n) => n.id === newNodeId);
    setSelectedNode(created || newNode);
    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
      }, 50);
    }

    if (sourceNode?.type === NODE_TYPES.ROUTER) {
      setTimeout(() => {
        setIntentPrompt({
          sourceId: addNodeMenu.sourceId,
          targetId: newNodeId,
          currentText: '',
        });
      }, 50);
    }
  };

  const handleIntentSave = () => {
    if (!intentPrompt) return;
    onUpdateNode(intentPrompt.sourceId, {
      ...nodes.find((n) => n.id === intentPrompt.sourceId)?.data,
      routing_options: {
        ...((nodes.find((n) => n.id === intentPrompt.sourceId)?.data?.routing_options as Record<string, string>) || {}),
        [intentPrompt.targetId]: intentPrompt.currentText || `Route to ${intentPrompt.targetId}`,
      },
    });
    setIntentPrompt(null);
  };

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!reactFlowInstance) return;

      const type = event.dataTransfer.getData('application/reactflow');
      if (!type || !DROPPABLE_NODE_TYPES.includes(type)) return;
      const nodeType = type as AddableNodeType;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const prefix = getNodeTypeDefinition(nodeType)?.prefix ?? 'node';
      const newId = nextUniqueId(prefix, nodes);

      const isFirstAgent =
        nodeType === NODE_TYPES.AGENT && nodes.filter((n) => n.type === NODE_TYPES.AGENT).length === 0;

      // Dropped nodes use a shorter agent job and also carry isStartNode / yaml_file
      const newNode = createWorkflowNode(nodeType, newId, position, {
        job: nodeType === NODE_TYPES.AGENT ? 'Processes tasks and inputs.' : undefined,
        isStartNode: isFirstAgent,
        yaml_file: nodeType === NODE_TYPES.SUBWORKFLOW ? '' : undefined,
      });

      insertNode(newNode, isFirstAgent);
    },
    [reactFlowInstance, nodes, insertNode]
  );

  // Replace the canvas with a quick-start template
  const loadTemplate = useCallback(
    ({ nodes: templateNodes, edges: templateEdges }: WorkflowTemplate) => {
      const layouted = getLayoutedElements(templateNodes, templateEdges, 'LR');
      setNodes(layouted.nodes);
      setEdges(layouted.edges);
      updateYaml(layouted.nodes, layouted.edges);
      if (reactFlowInstance) {
        setTimeout(() => {
          reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
        }, 50);
      }
    },
    [reactFlowInstance, setNodes, setEdges, updateYaml]
  );

  // Template loader: Linear
  const handleLoadLinearTemplate = useCallback(() => loadTemplate(createLinearTemplate()), [loadTemplate]);

  // Template loader: Router
  const handleLoadRouterTemplate = useCallback(() => loadTemplate(createRouterTemplate()), [loadTemplate]);

  return (
    <div className="border-border bg-background flex h-full w-full overflow-hidden rounded-lg border">
      <ReactFlowProvider>
        {/* ACTIVE WORKFLOW PALETTE & OUTLINE SIDEBAR */}
        <Sidebar
          nodes={nodes}
          selectedNodeId={selectedNode?.id}
          startAgentName={startAgentName}
          onSelectNode={(nodeId) => {
            const found = nodes.find((n) => n.id === nodeId);
            if (found) {
              setSelectedNode(found);
              if (reactFlowInstance) {
                reactFlowInstance.setCenter(found.position.x + 140, found.position.y + 70, { zoom: 1, duration: 400 });
              }
            }
          }}
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
            startAgentName={startAgentName}
            showDataWires={showDataWires}
            onAddAgent={handleAddAgent}
            onAddRouter={handleAddRouter}
            onAddFunction={handleAddFunction}
            onAddIterator={handleAddIterator}
            onAddSubworkflow={handleAddSubworkflow}
            onAutoLayout={handleAutoLayout}
            onToggleDataWires={() => setShowDataWires((prev) => !prev)}
            onFitView={() => reactFlowInstance?.fitView({ padding: 0.2, duration: 300 })}
          />

          <ReactFlow
            nodes={nodesWithHandlers}
            edges={visibleEdges}
            onlyRenderVisibleElements={true}
            // minZoom={0.1}
            maxZoom={2}
            defaultEdgeOptions={{
              type: 'smoothstep',
            }}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectEnd={onConnectEnd}
            onInit={setReactFlowInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={(_, node) => setSelectedNode(node)}
            onPaneClick={() => setSelectedNode(null)}
            onEdgeClick={(_, edge) => {
              const sourceNode = nodes.find((n) => n.id === edge.source);
              if (sourceNode?.type === NODE_TYPES.ROUTER) {
                const existingIntent =
                  (sourceNode.data?.routing_options as Record<string, string>)?.[edge.target] || '';
                setIntentPrompt({
                  sourceId: edge.source,
                  targetId: edge.target,
                  currentText: existingIntent,
                });
              }
            }}
            nodeTypes={nodeTypes}
            fitView
            className="bg-transparent"
          >
            <Background color="hsl(var(--border))" gap={20} size={1} variant={BackgroundVariant.Dots} />
            <Controls className="bg-card border-border fill-foreground" />

            {/* CANVAS LEGEND */}
            <CanvasLegend showDataWires={showDataWires} />
          </ReactFlow>

          {/* EMPTY CANVAS WELCOME & QUICK TEMPLATES */}
          {nodes.length === 0 && (
            <EmptyCanvasWelcome
              onLoadLinearTemplate={handleLoadLinearTemplate}
              onLoadRouterTemplate={handleLoadRouterTemplate}
              onAddAgent={handleAddAgent}
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
          onClose={() => setSelectedNode(null)}
          onUpdateNode={onUpdateNode}
          onRenameNode={onRenameNode}
          nodes={nodes}
          onSetStartAgent={handleSetStartAgent}
          onDeleteNode={handleDeleteNode}
        />
      </ReactFlowProvider>
    </div>
  );
};
