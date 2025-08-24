import React, { useCallback, useMemo } from 'react';
import ReactFlow, {
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  NodeTypes,
  EdgeTypes,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { useDesignerStore } from '@/store/designerStore';
import AgentNode from './AgentNode';
import ToolNode from './ToolNode';
import RouterNode from './RouterNode';
import CustomEdge from './CustomEdge';
import { FileText } from 'lucide-react';

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
  router: RouterNode,
};

const edgeTypes: EdgeTypes = {
  custom: CustomEdge,
};

const FlowCanvas: React.FC = () => {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    setSelectedNode,
    setSelectedEdge,
  } = useDesignerStore();

  const [localNodes, setLocalNodes, onLocalNodesChange] = useNodesState(nodes);
  const [localEdges, setLocalEdges, onLocalEdgesChange] = useEdgesState(edges);

  // Sync store state with local state
  React.useEffect(() => {
    setLocalNodes(nodes);
  }, [nodes, setLocalNodes]);

  React.useEffect(() => {
    setLocalEdges(edges.map(edge => ({ ...edge, type: 'custom' })));
  }, [edges, setLocalEdges]);

  const handleNodesChange = useCallback((changes: any) => {
    onLocalNodesChange(changes);
    onNodesChange(changes);
  }, [onLocalNodesChange, onNodesChange]);

  const handleEdgesChange = useCallback((changes: any) => {
    onLocalEdgesChange(changes);
    onEdgesChange(changes);
  }, [onLocalEdgesChange, onEdgesChange]);

  const handleConnect = useCallback((connection: Connection) => {
    const newEdge = { ...connection, type: 'custom', data: {} };
    setLocalEdges((eds) => addEdge(newEdge, eds));
    onConnect(connection);
  }, [setLocalEdges, onConnect]);

  const handleNodeClick = useCallback((event: React.MouseEvent, node: any) => {
    setSelectedNode(node);
  }, [setSelectedNode]);

  const handleEdgeClick = useCallback((event: React.MouseEvent, edge: any) => {
    setSelectedEdge(edge);
  }, [setSelectedEdge]);

  const handlePaneClick = useCallback(() => {
    setSelectedNode(undefined);
    setSelectedEdge(undefined);
  }, [setSelectedNode, setSelectedEdge]);

  const proOptions = useMemo(() => ({ hideAttribution: true }), []);

  // Show empty state if no nodes
  if (localNodes.length === 0) {
    return (
      <div className="w-full h-full bg-gray-50 flex items-center justify-center">
        <div className="text-center text-gray-500 px-4">
          <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium mb-2">Start Building Your Workflow</h3>
          <p className="text-sm max-w-md mx-auto">
            Create agents, connect them with tools, and build powerful AI workflows. 
            Click "Agent" in the toolbar to get started.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={localNodes}
        edges={localEdges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        connectionLineType="bezier"
        fitView
        proOptions={proOptions}
        className="bg-gray-50"
      >
        <Controls className="bg-white" />
        <Background color="#e2e8f0" gap={20} />
      </ReactFlow>
    </div>
  );
};

export default FlowCanvas;
