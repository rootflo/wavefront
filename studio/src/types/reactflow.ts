import { Node, Edge } from 'reactflow';
import { Agent, Tool, Router } from './agent';

export interface AgentNodeData {
  agent: Agent;
  isStart?: boolean;
  isEnd?: boolean;
}

export interface ToolNodeData {
  tool: Tool;
  isEnd?: boolean;
}

export interface RouterNodeData {
  router: Router;
  isEnd?: boolean;
}

export type CustomNode = Node<AgentNodeData | ToolNodeData | RouterNodeData>;

export interface CustomEdgeData {
  router?: string;
  label?: string;
  description?: string;
}

export type CustomEdge = Edge<CustomEdgeData>;

export type NodeType = 'agent' | 'tool' | 'router';

export interface FlowState {
  nodes: CustomNode[];
  edges: CustomEdge[];
  selectedNode?: CustomNode;
  selectedEdge?: CustomEdge;
}
