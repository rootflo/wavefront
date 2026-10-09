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
  Panel,
  Connection,
  Edge,
  Node,
  ReactFlowInstance,
  OnConnectEnd,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { Plus, Sparkles, Bot, GitBranch, Cpu, ArrowRight, Layers, Maximize2, Filter } from 'lucide-react';
import { Button } from '@app/components/ui/button';
import { Badge } from '@app/components/ui/badge';
import { Sidebar } from './Sidebar';
import { PropertyPanel } from './PropertyPanel';
import { AgentNode, RouterNode, TriggerNode, FunctionNode, IteratorNode, SubworkflowNode } from './nodes/CustomNodes';
import { parseYamlToGraph, serializeGraphToYaml, getLayoutedElements } from './yamlSync';

// Setup custom nodes mapping
const nodeTypes = {
  triggerNode: TriggerNode,
  agentNode: AgentNode,
  routerNode: RouterNode,
  functionNode: FunctionNode,
  iteratorNode: IteratorNode,
  subworkflowNode: SubworkflowNode,
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
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [showDataWires, setShowDataWires] = useState<boolean>(false);

  const [addNodeMenu, setAddNodeMenu] = useState<{ x: number; y: number; sourceId: string } | null>(null);
  const [intentPrompt, setIntentPrompt] = useState<{ sourceId: string; targetId: string; currentText: string } | null>(
    null
  );

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
    const firstAgent = nodes.find((n) => n.type === 'agentNode');
    return firstAgent?.id || '';
  }, [edges, nodes]);

  // Update a single node's data
  const onUpdateNode = useCallback(
    (id: string, data: Record<string, unknown>) => {
      setNodes((nds) => {
        const newNodes = nds.map((node) => {
          if (node.id === id) {
            const updated = { ...node, data };
            if (selectedNode?.id === id) {
              setSelectedNode(updated);
            }
            return updated;
          }
          return node;
        });
        updateYaml(newNodes, edges);
        return newNodes;
      });
    },
    [selectedNode, setNodes, updateYaml, edges]
  );

  // Rename a node and propagate new ID across edges and router routing_options
  const onRenameNode = useCallback(
    (oldId: string, newId: string) => {
      setNodes((nds) => {
        const newNodes = nds.map((node) => {
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
          if (node.type === 'iteratorNode' && node.data?.execute_node === oldId) {
            return {
              ...node,
              data: {
                ...node.data,
                execute_node: newId,
              },
            };
          }
          // If it's a router with routing_options containing oldId, rename the branch key
          if (node.type === 'routerNode' && node.data?.routing_options) {
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

        setEdges((eds) => {
          const newEdges = eds.map((edge) => {
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
          const remainingEdges = eds.filter((e) => e.source !== nodeId && e.target !== nodeId);

          // Clean up routing options in any router targeting the deleted node
          remainingNodes.forEach((node) => {
            if (node.type === 'routerNode' && node.data?.routing_options) {
              const opts = { ...(node.data.routing_options as Record<string, string>) };
              if (opts[nodeId]) {
                delete opts[nodeId];
                node.data.routing_options = opts;
              }
            }
          });

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
          type: 'triggerNode',
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
          pathOptions: { borderRadius: 16 },
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
    const count = nodes.filter((n) => n.type === 'agentNode').length + 1;
    const newId = `agent_${count}`;
    const isFirstAgent = nodes.filter((n) => n.type === 'agentNode').length === 0;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 250, y: 150 };

    insertNode(
      {
        id: newId,
        type: 'agentNode',
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
    const count = nodes.filter((n) => n.type === 'routerNode').length + 1;
    const newId = `router_${count}`;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: 'routerNode',
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
    const count = nodes.filter((n) => n.type === 'functionNode').length + 1;
    const newId = `function_${count}`;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: 'functionNode',
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
    const count = nodes.filter((n) => n.type === 'iteratorNode').length + 1;
    const newId = `iterator_${count}`;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: 'iteratorNode',
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
    const count = nodes.filter((n) => n.type === 'subworkflowNode').length + 1;
    const newId = `subworkflow_${count}`;

    const lastNode = nodes[nodes.length - 1];
    const position = lastNode ? { x: lastNode.position.x + 360, y: lastNode.position.y } : { x: 300, y: 150 };

    insertNode({
      id: newId,
      type: 'subworkflowNode',
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
  useEffect(() => {
    let edgesChanged = false;
    let newEdges = [...edges];
    let removedEdges = false;

    // 1. Add missing orange edges
    nodes
      .filter((n) => n.type === 'routerNode')
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
              labelStyle: { fill: '#f97316', fontWeight: 600, fontSize: 10, fontFamily: 'inherit' },
              labelBgPadding: [6, 4] as [number, number],
              labelBgBorderRadius: 4,
              labelBgStyle: { fill: 'hsl(var(--background))', stroke: '#border', strokeWidth: 1 },
              style: { stroke: '#f97316', strokeWidth: 2 },
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
      if (edge.style?.stroke === '#f97316') {
        const routerNode = nodes.find((n) => n.id === edge.source);
        if (routerNode && routerNode.type === 'routerNode') {
          const opts = (routerNode.data.routing_options as Record<string, string>) || {};
          if (!opts[edge.target]) {
            removedEdges = true;
            return false;
          }
        }
      }
      return true;
    });

    if (edgesChanged || removedEdges) {
      setEdges(newEdges);
      updateYaml(nodes, newEdges);
    }
  }, [nodes, edges, setEdges, updateYaml]);

  // Connection handler
  const onConnect = useCallback(
    (params: Connection | Edge) => {
      const sourceNode = nodes.find((n) => n.id === params.source);
      const isRouter = sourceNode?.type === 'routerNode';

      setEdges((eds) => {
        const newEdges = addEdge(
          {
            ...params,
            type: 'smoothstep',
            pathOptions: { borderRadius: 16 },
            style: {
              stroke: isRouter ? '#f97316' : '#64748b',
              strokeWidth: 2,
            },
            animated: !isRouter,
          },
          eds
        );
        updateYaml(nodes, newEdges);
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
    [nodes, setEdges, updateYaml]
  );

  const onConnectEnd: OnConnectEnd = useCallback((event, connectionState) => {
    if (!connectionState.isValid && connectionState.fromNode) {
      const clientX = 'clientX' in event ? event.clientX : (event.touches[0]?.clientX ?? 0);
      const clientY = 'clientY' in event ? event.clientY : (event.touches[0]?.clientY ?? 0);
      setAddNodeMenu({ x: clientX, y: clientY, sourceId: connectionState.fromNode.id });
    }
  }, []);

  const handleQuickAdd = (type: 'agentNode' | 'routerNode' | 'functionNode' | 'iteratorNode' | 'subworkflowNode') => {
    if (!addNodeMenu || !reactFlowInstance) return;
    const position = reactFlowInstance.screenToFlowPosition({ x: addNodeMenu.x, y: addNodeMenu.y });

    const count = nodes.filter((n) => n.type === type).length + 1;
    let newNodeId = `step_${count}`;
    if (type === 'agentNode') newNodeId = `agent_${count}`;
    else if (type === 'routerNode') newNodeId = `router_${count}`;
    else if (type === 'functionNode') newNodeId = `function_${count}`;
    else if (type === 'iteratorNode') newNodeId = `iterator_${count}`;
    else if (type === 'subworkflowNode') newNodeId = `subworkflow_${count}`;

    const newNode: Node = {
      id: newNodeId,
      type,
      position,
      data: {
        label: newNodeId,
        strategy: type === 'routerNode' ? 'smart' : undefined,
        role: type === 'agentNode' ? 'General Assistant' : undefined,
        job: type === 'agentNode' ? 'Processes inputs and generates responses.' : undefined,
        provider: type === 'agentNode' || type === 'routerNode' ? 'openai' : undefined,
        model: type === 'agentNode' || type === 'routerNode' ? 'gpt-4o-mini' : undefined,
        temperature: type === 'agentNode' ? 0.7 : type === 'routerNode' ? 0.3 : undefined,
        routing_options: type === 'routerNode' ? {} : undefined,
        function_name: type === 'functionNode' ? 'passthrough' : undefined,
        execute_node: type === 'iteratorNode' ? '' : undefined,
      },
    };

    const newEdge: Edge = {
      id: `e-${addNodeMenu.sourceId}-${newNodeId}`,
      source: addNodeMenu.sourceId,
      target: newNodeId,
      type: 'smoothstep',
      pathOptions: { borderRadius: 16 },
      style: {
        stroke: nodes.find((n) => n.id === addNodeMenu.sourceId)?.type === 'routerNode' ? '#f97316' : '#64748b',
        strokeWidth: 2,
      },
    };

    const newNodes = [...nodes, newNode];
    const newEdges = [...edges, newEdge];
    const layouted = getLayoutedElements(newNodes, newEdges, 'LR');
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

    const sourceNode = nodes.find((n) => n.id === addNodeMenu.sourceId);
    if (sourceNode?.type === 'routerNode') {
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
      const validTypes = ['agentNode', 'routerNode', 'functionNode', 'iteratorNode', 'subworkflowNode'];
      if (!type || !validTypes.includes(type)) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const count = nodes.filter((n) => n.type === type).length + 1;
      let newId = `node_${count}`;
      if (type === 'agentNode') newId = `agent_${count}`;
      else if (type === 'routerNode') newId = `router_${count}`;
      else if (type === 'functionNode') newId = `function_${count}`;
      else if (type === 'iteratorNode') newId = `iterator_${count}`;
      else if (type === 'subworkflowNode') newId = `subworkflow_${count}`;

      const isFirstAgent = type === 'agentNode' && nodes.filter((n) => n.type === 'agentNode').length === 0;

      const newNode: Node = {
        id: newId,
        type,
        position,
        data: {
          label: newId,
          role: type === 'agentNode' ? 'General Assistant' : undefined,
          job: type === 'agentNode' ? 'Processes tasks and inputs.' : undefined,
          provider: type === 'agentNode' || type === 'routerNode' ? 'openai' : undefined,
          model: type === 'agentNode' || type === 'routerNode' ? 'gpt-4o-mini' : undefined,
          temperature: type === 'agentNode' ? 0.7 : type === 'routerNode' ? 0.3 : undefined,
          strategy: type === 'routerNode' ? 'smart' : undefined,
          routing_options: type === 'routerNode' ? {} : undefined,
          isStartNode: isFirstAgent,
          function_name: type === 'functionNode' ? 'passthrough' : undefined,
          execute_node: type === 'iteratorNode' ? '' : undefined,
          yaml_file: type === 'subworkflowNode' ? '' : undefined,
        },
      };

      insertNode(newNode, isFirstAgent);
    },
    [reactFlowInstance, nodes, insertNode]
  );

  // Template loader: Linear
  const handleLoadLinearTemplate = useCallback(() => {
    const templateNodes: Node[] = [
      {
        id: 'trigger-start',
        type: 'triggerNode',
        position: { x: 50, y: 150 },
        data: { label: 'Workflow Trigger', description: 'Triggers the linear flow.', type: 'trigger' },
      },
      {
        id: 'content_creator',
        type: 'agentNode',
        position: { x: 400, y: 150 },
        data: {
          label: 'content_creator',
          role: 'Content Creator',
          job: 'Drafts high quality articles and posts based on inputs.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.7,
          isStartNode: true,
          type: 'agent',
        },
      },
      {
        id: 'editor',
        type: 'agentNode',
        position: { x: 750, y: 150 },
        data: {
          label: 'editor',
          role: 'Editor',
          job: 'Polishes, edits, and checks grammar and tone.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.3,
          type: 'agent',
        },
      },
    ];

    const templateEdges: Edge[] = [
      {
        id: 'e-start-content_creator',
        source: 'trigger-start',
        target: 'content_creator',
        animated: true,
        style: { stroke: '#a855f7', strokeWidth: 2 },
      },
      {
        id: 'e-content_creator-editor',
        source: 'content_creator',
        target: 'editor',
        animated: true,
        style: { stroke: '#888888', strokeWidth: 2 },
      },
    ];

    const layouted = getLayoutedElements(templateNodes, templateEdges, 'LR');
    setNodes(layouted.nodes);
    setEdges(layouted.edges);
    updateYaml(layouted.nodes, layouted.edges);
    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
      }, 50);
    }
  }, [reactFlowInstance, setNodes, setEdges, updateYaml]);

  // Template loader: Router
  const handleLoadRouterTemplate = useCallback(() => {
    const templateNodes: Node[] = [
      {
        id: 'trigger-start',
        type: 'triggerNode',
        position: { x: 50, y: 150 },
        data: { label: 'Workflow Trigger', description: 'Triggers request triage.', type: 'trigger' },
      },
      {
        id: 'triage_agent',
        type: 'agentNode',
        position: { x: 400, y: 150 },
        data: {
          label: 'triage_agent',
          role: 'Support Triage',
          job: 'Understands customer inquiry and normalizes details.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.5,
          isStartNode: true,
          type: 'agent',
        },
      },
      {
        id: 'intent_router',
        type: 'routerNode',
        position: { x: 750, y: 150 },
        data: {
          label: 'intent_router',
          strategy: 'smart',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.2,
          routing_options: {
            tech_specialist: 'Technical or API troubleshooting',
            billing_agent: 'Billing & payment requests',
          },
          type: 'router',
        },
      },
      {
        id: 'tech_specialist',
        type: 'agentNode',
        position: { x: 1100, y: 50 },
        data: {
          label: 'tech_specialist',
          role: 'Technical Engineer',
          job: 'Fixes bugs and answers deep technical inquiries.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.4,
          type: 'agent',
        },
      },
      {
        id: 'billing_agent',
        type: 'agentNode',
        position: { x: 1100, y: 250 },
        data: {
          label: 'billing_agent',
          role: 'Billing Specialist',
          job: 'Handles invoices, refunds, and subscriptions.',
          provider: 'openai',
          model: 'gpt-4o-mini',
          temperature: 0.3,
          type: 'agent',
        },
      },
    ];

    const templateEdges: Edge[] = [
      {
        id: 'e-start-triage_agent',
        source: 'trigger-start',
        target: 'triage_agent',
        animated: true,
        style: { stroke: '#a855f7', strokeWidth: 2 },
      },
      {
        id: 'e-triage_agent-intent_router',
        source: 'triage_agent',
        target: 'intent_router',
        animated: true,
        style: { stroke: '#888888', strokeWidth: 2 },
      },
      {
        id: 'e-intent_router-tech_specialist',
        source: 'intent_router',
        target: 'tech_specialist',
        label: 'Technical or API troubleshooting',
        labelStyle: { fill: '#f97316', fontWeight: 600, fontSize: 10 },
        labelBgPadding: [6, 4] as [number, number],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: 'hsl(var(--background))', stroke: '#border', strokeWidth: 1 },
        style: { stroke: '#f97316', strokeWidth: 2 },
      },
      {
        id: 'e-intent_router-billing_agent',
        source: 'intent_router',
        target: 'billing_agent',
        label: 'Billing & payment requests',
        labelStyle: { fill: '#f97316', fontWeight: 600, fontSize: 10 },
        labelBgPadding: [6, 4] as [number, number],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: 'hsl(var(--background))', stroke: '#border', strokeWidth: 1 },
        style: { stroke: '#f97316', strokeWidth: 2 },
      },
    ];

    const layouted = getLayoutedElements(templateNodes, templateEdges, 'LR');
    setNodes(layouted.nodes);
    setEdges(layouted.edges);
    updateYaml(layouted.nodes, layouted.edges);
    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ padding: 0.2, duration: 400 });
      }, 50);
    }
  }, [reactFlowInstance, setNodes, setEdges, updateYaml]);

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
          <div className="bg-card/95 border-border absolute top-3 left-4 z-20 flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 shadow-md backdrop-blur-md">
            <Button
              size="sm"
              variant="outline"
              onClick={handleAddAgent}
              className="h-7 gap-1 border-emerald-500/30 text-xs font-medium text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
            >
              <Bot size={13} /> + Agent
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleAddRouter}
              className="h-7 gap-1 border-orange-500/30 text-xs font-medium text-orange-600 hover:bg-orange-500/10 dark:text-orange-400"
            >
              <GitBranch size={13} /> + Router
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleAddFunction}
              className="h-7 gap-1 border-blue-500/30 text-xs font-medium text-blue-600 hover:bg-blue-500/10 dark:text-blue-400"
            >
              <Cpu size={13} /> + Function
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleAddIterator}
              className="h-7 gap-1 border-indigo-500/30 text-xs font-medium text-indigo-600 hover:bg-indigo-500/10 dark:text-indigo-400"
            >
              <ArrowRight size={13} /> + Iterator
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleAddSubworkflow}
              className="h-7 gap-1 border-teal-500/30 text-xs font-medium text-teal-600 hover:bg-teal-500/10 dark:text-teal-400"
            >
              <Layers size={13} /> + Sub-Flow
            </Button>

            <div className="bg-border mx-1 my-auto h-4 w-[1px]" />

            <Button
              size="sm"
              variant="ghost"
              onClick={handleAutoLayout}
              className="text-muted-foreground hover:text-foreground h-7 gap-1 text-xs font-medium"
              title="Automatically align and organize all blocks horizontally with zero overlap"
            >
              <Sparkles size={13} /> Re-align
            </Button>

            <Button
              size="sm"
              variant={showDataWires ? 'secondary' : 'ghost'}
              onClick={() => setShowDataWires((prev) => !prev)}
              className={`h-7 gap-1 text-xs font-medium ${
                showDataWires
                  ? 'border border-blue-500/30 bg-blue-500/10 text-blue-500'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              title={
                showDataWires ? 'Hide background memory wires (show only focused)' : 'Show all memory filter wires'
              }
            >
              <Filter size={12} /> {showDataWires ? 'Data Wires: All' : 'Data Wires: Focus'}
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => reactFlowInstance?.fitView({ padding: 0.2, duration: 300 })}
              className="text-muted-foreground hover:text-foreground h-7 gap-1 text-xs font-medium"
              title="Fit entire flow to screen"
            >
              <Maximize2 size={13} /> Fit
            </Button>

            {startAgentName && (
              <Badge
                variant="outline"
                className="ml-1 border-emerald-500/30 bg-emerald-500/10 py-0.5 text-[10px] text-emerald-600 dark:text-emerald-400"
              >
                🚀 Start: {(nodes.find((n) => n.id === startAgentName)?.data?.label as string) || startAgentName}
              </Badge>
            )}
          </div>

          <ReactFlow
            nodes={nodesWithHandlers}
            edges={visibleEdges}
            onlyRenderVisibleElements={true}
            // minZoom={0.1}
            maxZoom={2}
            defaultEdgeOptions={{
              type: 'smoothstep',
              pathOptions: { borderRadius: 16 },
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
              if (sourceNode?.type === 'routerNode') {
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
            <Panel
              position="bottom-left"
              className="bg-card/95 border-border mb-4 ml-4 flex max-w-[220px] flex-col gap-1.5 rounded-xl border p-3 shadow-lg backdrop-blur-md"
            >
              <h4 className="text-foreground mb-0.5 text-[11px] font-semibold tracking-wider uppercase">Flow Legend</h4>
              <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
                <div className="h-0.5 w-3.5 bg-purple-500"></div>
                <span>Start Trigger</span>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
                <div className="h-0.5 w-3.5 bg-slate-500"></div>
                <span>Sequential Flow</span>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
                <div className="h-0.5 w-3.5 bg-orange-500"></div>
                <span>Router Branch</span>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
                <div className="h-0.5 w-3.5 border-t border-dashed border-blue-500"></div>
                <span>Data Filter ({showDataWires ? 'All shown' : 'Click node to view'})</span>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-[10px]">
                <div className="h-0.5 w-3.5 bg-indigo-500"></div>
                <span>ForEach Loop Target</span>
              </div>
            </Panel>
          </ReactFlow>

          {/* EMPTY CANVAS WELCOME & QUICK TEMPLATES */}
          {nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center p-4">
              <div className="bg-card/95 border-border pointer-events-auto flex max-w-md flex-col items-center gap-4 rounded-2xl border border-dashed p-8 text-center shadow-2xl backdrop-blur-md">
                <div className="bg-primary/10 text-primary flex h-12 w-12 items-center justify-center rounded-xl shadow-xs">
                  <Bot size={24} />
                </div>
                <div>
                  <h3 className="text-foreground text-sm font-semibold">Canvas is Empty</h3>
                  <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                    Drag components from the sidebar or jumpstart with a pre-configured template:
                  </p>
                </div>

                <div className="flex w-full flex-col gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleLoadLinearTemplate}
                    className="border-border h-9 w-full justify-start gap-2 text-xs hover:border-emerald-500/50 hover:bg-emerald-500/5"
                  >
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    <strong>Linear Pipeline:</strong> Content Creator ➔ Editor
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleLoadRouterTemplate}
                    className="border-border h-9 w-full justify-start gap-2 text-xs hover:border-orange-500/50 hover:bg-orange-500/5"
                  >
                    <span className="h-2 w-2 rounded-full bg-orange-500" />
                    <strong>Smart Routing:</strong> Triage ➔ Intent Router ➔ 2 Specialists
                  </Button>
                </div>

                <div className="border-border/60 w-full border-t pt-3">
                  <Button size="sm" onClick={handleAddAgent} className="w-full gap-1.5 text-xs font-medium">
                    <Plus size={13} /> Add Blank Agent
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* QUICK ADD POPUP (ON DRAGGING EDGE INTO EMPTY CANVAS) */}
          {addNodeMenu && (
            <div
              className="bg-card border-border animate-in fade-in zoom-in-95 absolute z-50 flex w-52 flex-col gap-1 rounded-xl border p-2 shadow-xl duration-100"
              style={{ top: Math.max(10, addNodeMenu.y - 140), left: Math.max(10, addNodeMenu.x - 290) }}
            >
              <div className="text-muted-foreground px-2 py-1 text-[10px] font-bold tracking-wider uppercase">
                Quick Add Step
              </div>
              <button
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-emerald-600 transition-colors hover:bg-emerald-500/10 dark:text-emerald-400"
                onClick={() => handleQuickAdd('agentNode')}
              >
                <Bot size={13} /> + Add Agent
              </button>
              <button
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-orange-600 transition-colors hover:bg-orange-500/10 dark:text-orange-400"
                onClick={() => handleQuickAdd('routerNode')}
              >
                <GitBranch size={13} /> + Add Router
              </button>
              <button
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-blue-600 transition-colors hover:bg-blue-500/10 dark:text-blue-400"
                onClick={() => handleQuickAdd('functionNode')}
              >
                <Cpu size={13} /> + Add Function
              </button>
              <button
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-500/10 dark:text-indigo-400"
                onClick={() => handleQuickAdd('iteratorNode')}
              >
                <ArrowRight size={13} /> + Add Iterator
              </button>
              <button
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-teal-600 transition-colors hover:bg-teal-500/10 dark:text-teal-400"
                onClick={() => handleQuickAdd('subworkflowNode')}
              >
                <Layers size={13} /> + Add Sub-Workflow
              </button>
            </div>
          )}

          {/* INTENT PROMPT MODAL (ON CONNECTING ROUTER TO AGENT OR CLICKING ROUTE EDGE) */}
          {intentPrompt && (
            <div className="bg-background/60 absolute inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs">
              <div className="bg-card border-border animate-in fade-in zoom-in-95 flex w-[420px] flex-col overflow-hidden rounded-2xl border shadow-2xl duration-150">
                <div className="border-b border-orange-500/20 bg-orange-500/10 px-5 py-3.5">
                  <h3 className="text-xs font-semibold tracking-wider text-orange-600 uppercase dark:text-orange-400">
                    Define Routing Condition
                  </h3>
                  {(() => {
                    const sourceLabel =
                      nodes.find((n) => n.id === intentPrompt.sourceId)?.data?.label || intentPrompt.sourceId;
                    const targetLabel =
                      nodes.find((n) => n.id === intentPrompt.targetId)?.data?.label || intentPrompt.targetId;
                    return (
                      <p className="text-foreground/80 mt-1 text-xs">
                        When should <strong>{sourceLabel as string}</strong> route to{' '}
                        <strong>{targetLabel as string}</strong>?
                      </p>
                    );
                  })()}
                </div>
                <div className="flex flex-col gap-3 p-5">
                  <textarea
                    autoFocus
                    className="bg-background border-border text-foreground h-24 w-full resize-none rounded-lg border px-3 py-2 text-xs leading-relaxed focus:border-orange-500 focus:outline-none"
                    placeholder="e.g. When the user asks for technical documentation or code examples..."
                    value={intentPrompt.currentText}
                    onChange={(e) => setIntentPrompt({ ...intentPrompt, currentText: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleIntentSave();
                      }
                    }}
                  />
                  <div className="flex items-center justify-end gap-2 pt-1">
                    <button
                      className="hover:bg-muted text-muted-foreground rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                      onClick={() => setIntentPrompt(null)}
                    >
                      Skip
                    </button>
                    <button
                      className="rounded-lg bg-orange-600 px-3.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-700"
                      onClick={handleIntentSave}
                    >
                      Save Rule (↵)
                    </button>
                  </div>
                </div>
              </div>
            </div>
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
