import { create } from 'zustand';
import { Node, Edge, addEdge, Connection, applyNodeChanges, applyEdgeChanges, NodeChange, EdgeChange } from 'reactflow';
import { Agent, Tool, Router, DesignerConfig } from '@/types/agent';
import { CustomNode, CustomEdge, AgentNodeData, ToolNodeData, RouterNodeData } from '@/types/reactflow';

interface DesignerState {
  // Configuration
  config: DesignerConfig;
  
  // Flow state
  nodes: CustomNode[];
  edges: CustomEdge[];
  
  // UI state
  selectedNode?: CustomNode;
  selectedEdge?: CustomEdge;
  isAgentEditorOpen: boolean;
  isEdgeEditorOpen: boolean;
  isConfigEditorOpen: boolean;
  isRouterEditorOpen: boolean;
  
  // Workflow metadata
  workflowName: string;
  workflowDescription: string;
  workflowVersion: string;
  
  // Actions
  setConfig: (config: DesignerConfig) => void;
  
  // Node actions
  addAgent: (agent: Agent, position: { x: number; y: number }) => void;
  addTool: (tool: Tool, position: { x: number; y: number }) => void;
  addRouter: (router: Router, position: { x: number; y: number }) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>) => void;
  updateRouter: (routerId: string, updates: Partial<Router>) => void;
  deleteNode: (nodeId: string) => void;
  setSelectedNode: (node?: CustomNode) => void;
  
  // Edge actions
  onConnect: (connection: Connection) => void;
  updateEdge: (edgeId: string, updates: Partial<CustomEdge>) => void;
  deleteEdge: (edgeId: string) => void;
  setSelectedEdge: (edge?: CustomEdge) => void;
  
  // Flow actions
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  
  // UI actions
  openAgentEditor: (node?: CustomNode) => void;
  closeAgentEditor: () => void;
  openRouterEditor: (node?: CustomNode) => void;
  closeRouterEditor: () => void;
  openEdgeEditor: (edge: CustomEdge) => void;
  closeEdgeEditor: () => void;
  openConfigEditor: () => void;
  closeConfigEditor: () => void;
  
  // Workflow metadata actions
  setWorkflowMetadata: (metadata: { name: string; description: string; version: string }) => void;
  
  // Utility actions
  clearWorkflow: () => void;
  loadWorkflow: (workflow: any) => void;
  importFromYAML: (yamlContent: string) => Promise<void>;
}

const defaultConfig: DesignerConfig = {
  availableTools: [
    { name: 'calculator', description: 'Perform mathematical calculations' },
    { name: 'web_search', description: 'Search the web for information' },
    { name: 'file_reader', description: 'Read and analyze files' },
    { name: 'email_sender', description: 'Send emails' },
    { name: 'text_processor', description: 'Process and analyze text content' },
    { name: 'image_analyzer', description: 'Analyze and process images' },
  ],
  availableLLMs: [
    { provider: 'openai', name: 'gpt-4o' },
    { provider: 'openai', name: 'gpt-4o-mini' },
    { provider: 'anthropic', name: 'claude-3-5-sonnet-20240620' },
    { provider: 'anthropic', name: 'claude-3-5-haiku-20241022' },
    { provider: 'gemini', name: 'gemini-2.5-flash' },
    { provider: 'gemini', name: 'gemini-2.5-pro' },
    { provider: 'ollama', name: 'llama2' },
    { provider: 'ollama', name: 'llama3' },
  ],
  availableRouters: [
    { 
      name: 'default_router', 
      description: 'Default router that passes to the next node',
      code: `def route(memory: BaseMemory) -> str:
    # Always route to the first available target
    return target_nodes[0]`
    },
    { 
      name: 'content_router', 
      description: 'Routes based on content analysis',
      code: `def route(memory: BaseMemory) -> str:
    content = str(memory.get()[-1]).lower()
    if 'technical' in content:
        return 'tech_specialist'
    elif 'business' in content:
        return 'business_specialist'
    return 'general_handler'`
    },
    { 
      name: 'classification_router', 
      description: 'Routes based on classification results',
      code: `def route(memory: BaseMemory) -> str:
    last_message = memory.get()[-1]
    if 'urgent' in str(last_message).lower():
        return 'priority_handler'
    elif 'routine' in str(last_message).lower():
        return 'standard_handler'
    return 'default_handler'`
    },
    { 
      name: 'sentiment_router', 
      description: 'Routes based on sentiment analysis',
      code: `def route(memory: BaseMemory) -> str:
    content = str(memory.get()[-1]).lower()
    positive_words = ['good', 'great', 'excellent', 'happy']
    negative_words = ['bad', 'terrible', 'angry', 'frustrated']
    
    if any(word in content for word in negative_words):
        return 'escalation_agent'
    elif any(word in content for word in positive_words):
        return 'satisfaction_agent'
    return 'neutral_agent'`
    },
  ],
};

export const useDesignerStore = create<DesignerState>((set, get) => ({
  // Initial state
  config: defaultConfig,
  nodes: [],
  edges: [],
  selectedNode: undefined,
  selectedEdge: undefined,
  isAgentEditorOpen: false,
  isEdgeEditorOpen: false,
  isConfigEditorOpen: false,
  isRouterEditorOpen: false,
  workflowName: 'New Workflow',
  workflowDescription: '',
  workflowVersion: '1.0.0',

  // Configuration actions
  setConfig: (config) => set({ config }),

  // Node actions
  addAgent: (agent, position) => {
    const newNode: CustomNode = {
      id: agent.id,
      type: 'agent',
      position,
      data: { agent } as AgentNodeData,
    };
    set((state) => ({
      nodes: [...state.nodes, newNode],
    }));
  },

  addTool: (tool, position) => {
    const newNode: CustomNode = {
      id: `tool_${tool.name}_${Date.now()}`,
      type: 'tool',
      position,
      data: { tool } as ToolNodeData,
    };
    set((state) => ({
      nodes: [...state.nodes, newNode],
    }));
  },

  addRouter: (router, position) => {
    const newNode: CustomNode = {
      id: router.id || `router_${router.name}_${Date.now()}`,
      type: 'router',
      position,
      data: { router } as RouterNodeData,
    };
    set((state) => ({
      nodes: [...state.nodes, newNode],
    }));
  },

  updateAgent: (agentId, updates) => {
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id === agentId && node.type === 'agent') {
          const agentData = node.data as AgentNodeData;
          return {
            ...node,
            data: {
              ...agentData,
              agent: { ...agentData.agent, ...updates },
            },
          };
        }
        return node;
      }),
    }));
  },

  updateRouter: (routerId, updates) => {
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id === routerId && node.type === 'router') {
          const routerData = node.data as RouterNodeData;
          return {
            ...node,
            data: {
              ...routerData,
              router: { ...routerData.router, ...updates },
            },
          };
        }
        return node;
      }),
    }));
  },

  deleteNode: (nodeId) => {
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== nodeId),
      edges: state.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
      selectedNode: state.selectedNode?.id === nodeId ? undefined : state.selectedNode,
    }));
  },

  setSelectedNode: (node) => set({ selectedNode: node }),

  // Edge actions
  onConnect: (connection) => {
    const newEdge: CustomEdge = {
      ...connection,
      id: `edge_${connection.source}_${connection.target}_${Date.now()}`,
      data: {},
    } as CustomEdge;

    set((state) => ({
      edges: addEdge(newEdge, state.edges),
    }));
  },

  updateEdge: (edgeId, updates) => {
    set((state) => ({
      edges: state.edges.map((edge) =>
        edge.id === edgeId ? { ...edge, ...updates } : edge
      ),
    }));
  },

  deleteEdge: (edgeId) => {
    set((state) => ({
      edges: state.edges.filter((edge) => edge.id !== edgeId),
      selectedEdge: state.selectedEdge?.id === edgeId ? undefined : state.selectedEdge,
    }));
  },

  setSelectedEdge: (edge) => set({ selectedEdge: edge }),

  // Flow actions
  onNodesChange: (changes) => {
    set((state) => ({
      nodes: applyNodeChanges(changes, state.nodes),
    }));
  },

  onEdgesChange: (changes) => {
    set((state) => ({
      edges: applyEdgeChanges(changes, state.edges),
    }));
  },

  // UI actions
  openAgentEditor: (node) => {
    set({ 
      isAgentEditorOpen: true,
      selectedNode: node,
    });
  },

  closeAgentEditor: () => set({ isAgentEditorOpen: false }),

  openRouterEditor: (node) => {
    set({ 
      isRouterEditorOpen: true,
      selectedNode: node,
    });
  },

  closeRouterEditor: () => set({ isRouterEditorOpen: false }),

  openEdgeEditor: (edge) => {
    set({ 
      isEdgeEditorOpen: true,
      selectedEdge: edge,
    });
  },

  closeEdgeEditor: () => set({ isEdgeEditorOpen: false }),

  openConfigEditor: () => set({ isConfigEditorOpen: true }),

  closeConfigEditor: () => set({ isConfigEditorOpen: false }),

  // Workflow metadata actions
  setWorkflowMetadata: (metadata) => {
    set({
      workflowName: metadata.name,
      workflowDescription: metadata.description,
      workflowVersion: metadata.version,
    });
  },

  // Utility actions
  clearWorkflow: () => {
    set({
      nodes: [],
      edges: [],
      selectedNode: undefined,
      selectedEdge: undefined,
      workflowName: 'New Workflow',
      workflowDescription: '',
      workflowVersion: '1.0.0',
    });
  },

  loadWorkflow: (workflow) => {
    // TODO: Implement workflow loading from YAML
    console.log('Loading workflow:', workflow);
  },

  importFromYAML: async (yamlContent) => {
    try {
      const { parseAriumYAML } = await import('@/utils/yamlImport');
      const result = parseAriumYAML(yamlContent);
      
      set({
        nodes: result.nodes,
        edges: result.edges,
        workflowName: result.workflowName,
        workflowDescription: result.workflowDescription,
        workflowVersion: result.workflowVersion,
        selectedNode: undefined,
        selectedEdge: undefined,
      });
    } catch (error) {
      console.error('Failed to import YAML:', error);
      throw error;
    }
  },
}));
