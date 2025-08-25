import { dump } from 'js-yaml';
import { Agent } from '@/types/agent';
import { CustomNode, CustomEdge } from '@/types/reactflow';

export interface ExportData {
  nodes: CustomNode[];
  edges: CustomEdge[];
  workflowName: string;
  workflowDescription: string;
  workflowVersion: string;
  startNodeId?: string;
  endNodeIds: string[];
}

// Utility function to convert names to snake_case
function toSnakeCase(str: string): string {
  return str
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')           // Replace spaces with underscores
    .replace(/[^a-z0-9_]/g, '')     // Remove special characters except underscores
    .replace(/_+/g, '_')            // Replace multiple underscores with single
    .replace(/^_|_$/g, '');         // Remove leading/trailing underscores
}

export function generateAriumYAML(data: ExportData): string {
  const { nodes, edges, workflowName, workflowDescription, workflowVersion, startNodeId, endNodeIds } = data;

  // Create mapping from node IDs to snake_case names
  const nodeIdToName = new Map<string, string>();
  
  // Extract agents, tools, and routers
  const agents: Agent[] = [];
  const tools: string[] = [];
  const routers: any[] = [];
  
  nodes.forEach((node) => {
    if (node.type === 'agent') {
      const agentData = node.data as any;
      const agent = agentData.agent;
      const snakeCaseName = toSnakeCase(agent.name);
      nodeIdToName.set(node.id, snakeCaseName);
      agents.push({
        ...agent,
        name: snakeCaseName, // Use snake_case name for YAML
      });
    } else if (node.type === 'tool') {
      const toolData = node.data as any;
      const toolName = toSnakeCase(toolData.tool.name);
      nodeIdToName.set(node.id, toolName);
      tools.push(toolName);
    } else if (node.type === 'router') {
      const routerData = node.data as any;
      const router = routerData.router;
      const snakeCaseName = toSnakeCase(router.name);
      nodeIdToName.set(node.id, snakeCaseName);
      routers.push({
        ...router,
        name: snakeCaseName, // Use snake_case name for YAML
      });
    }
  });

  // Determine start and end nodes (use user-defined or auto-detect)
  let finalStartNodeId = startNodeId;
  let finalEndNodeIds = [...endNodeIds];
  
  // If no user-defined start/end nodes, auto-detect from connections
  if (!finalStartNodeId || finalEndNodeIds.length === 0) {
    const nodeConnections = new Map<string, { incoming: string[], outgoing: string[] }>();
    
    // Initialize connections map
    nodes.forEach((node) => {
      nodeConnections.set(node.id, { incoming: [], outgoing: [] });
    });

    // Build connections
    edges.forEach((edge) => {
      const sourceConnections = nodeConnections.get(edge.source);
      const targetConnections = nodeConnections.get(edge.target);
      
      if (sourceConnections) {
        sourceConnections.outgoing.push(edge.target);
      }
      if (targetConnections) {
        targetConnections.incoming.push(edge.source);
      }
    });

    // Auto-detect start node if not set
    if (!finalStartNodeId) {
      const startNodes = nodes.filter((node) => {
        const connections = nodeConnections.get(node.id);
        return connections && connections.incoming.length === 0 && node.type !== 'router';
      });
      finalStartNodeId = startNodes[0]?.id;
    }

    // Auto-detect end nodes if none set
    if (finalEndNodeIds.length === 0) {
      const endNodes = nodes.filter((node) => {
        const connections = nodeConnections.get(node.id);
        return connections && connections.outgoing.length === 0 && node.type !== 'router';
      });
      finalEndNodeIds = endNodes.map(node => node.id);
    }
  }

  // Build workflow edges using snake_case names
  const workflowEdges: Array<{
    from: string;
    to: string[];
    router?: string;
  }> = [];

  // Group edges by source
  const edgesBySource = new Map<string, CustomEdge[]>();
  edges.forEach((edge) => {
    if (!edgesBySource.has(edge.source)) {
      edgesBySource.set(edge.source, []);
    }
    edgesBySource.get(edge.source)!.push(edge);
  });

  // Create workflow edges using names instead of IDs
  edgesBySource.forEach((sourceEdges, sourceId) => {
    const sourceName = nodeIdToName.get(sourceId);
    if (!sourceName) return; // Skip if source node not found
    
    const sourceNode = nodes.find(n => n.id === sourceId);
    
    // Handle agent nodes that connect to routers
    if (sourceNode?.type === 'agent') {
      // Check if this agent connects to a router
      const routerTargets = sourceEdges
        .map(edge => edge.target)
        .map(targetId => nodes.find(n => n.id === targetId))
        .filter(node => node?.type === 'router');
      
      if (routerTargets.length > 0) {
        // This agent connects through a router
        const routerNode = routerTargets[0];
        const routerName = nodeIdToName.get(routerNode!.id);
        
        // Find what the router connects to
        const routerEdges = edgesBySource.get(routerNode!.id) || [];
        const routerTargetNames = routerEdges
          .map(edge => nodeIdToName.get(edge.target))
          .filter(name => name !== undefined) as string[];
        
        // Create workflow edge with router
        if (routerTargetNames.length > 0) {
          workflowEdges.push({
            from: sourceName,
            to: routerTargetNames,
            router: routerName,
          });
        }
      } else {
        // Direct agent-to-agent connections
        const targets = sourceEdges.map((edge) => edge.target);
        const targetNames = targets
          .map(targetId => nodeIdToName.get(targetId))
          .filter(name => name !== undefined) as string[];
        
        // Skip router nodes as targets
        const agentTargetNames = targetNames.filter(name => {
          const targetNode = nodes.find(n => nodeIdToName.get(n.id) === name);
          return targetNode?.type !== 'router';
        });
        
        if (agentTargetNames.length > 0) {
          const workflowEdge: any = {
            from: sourceName,
            to: agentTargetNames,
          };
          
          // Check if edges have router data
          const routerNames = sourceEdges
            .map(edge => edge.data?.router)
            .filter(router => router !== undefined);
          
          if (routerNames.length > 0) {
            workflowEdge.router = routerNames[0];
          }
          
          workflowEdges.push(workflowEdge);
        }
      }
    }
  });

  // Note: workflowEdges already filters out router-only edges in the main logic above

  // Convert agents to YAML format
  const yamlAgents = agents.map((agent) => {
    const yamlAgent: any = {
      name: agent.name,
      role: agent.role,
      job: agent.job,
      model: {
        provider: agent.model.provider,
        name: agent.model.name,
      },
    };

    // Add base_url if present
    if (agent.model.base_url) {
      yamlAgent.model.base_url = agent.model.base_url;
    }

    // Add settings if present
    if (agent.settings) {
      yamlAgent.settings = {};
      if (agent.settings.temperature !== undefined) {
        yamlAgent.settings.temperature = agent.settings.temperature;
      }
      if (agent.settings.max_retries !== undefined) {
        yamlAgent.settings.max_retries = agent.settings.max_retries;
      }
      if (agent.settings.reasoning_pattern !== undefined) {
        yamlAgent.settings.reasoning_pattern = agent.settings.reasoning_pattern;
      }
    }

    // Add tools if present
    if (agent.tools && agent.tools.length > 0) {
      yamlAgent.tools = agent.tools;
    }

    // Add parser if present
    if (agent.parser && agent.parser.fields && agent.parser.fields.length > 0) {
      yamlAgent.parser = {
        name: agent.parser.name,
        version: agent.parser.version || '1.0.0',
        description: agent.parser.description,
        fields: agent.parser.fields.map((field) => ({
          name: field.name,
          type: field.type,
          description: field.description,
          required: field.required,
          values: field.values,
          items: field.items,
        })),
      };
    }

    return yamlAgent;
  });

  // Convert routers to YAML format
  const yamlRouters = routers.map((router) => {
    const yamlRouter: any = {
      name: router.name,
      type: router.type || 'smart',
    };

    if (router.routing_options && Object.keys(router.routing_options).length > 0) {
      // Convert routing option keys to snake_case
      yamlRouter.routing_options = {};
      Object.entries(router.routing_options).forEach(([key, value]) => {
        const snakeCaseKey = toSnakeCase(key);
        yamlRouter.routing_options[snakeCaseKey] = value;
      });
    }

    if (router.task_categories && Object.keys(router.task_categories).length > 0) {
      yamlRouter.task_categories = router.task_categories;
    }

    if (router.flow_pattern && router.flow_pattern.length > 0) {
      yamlRouter.flow_pattern = router.flow_pattern;
    }

    if (router.model) {
      yamlRouter.model = {
        provider: router.model.provider,
        name: router.model.name,
      };
    }

    if (router.settings) {
      yamlRouter.settings = {};
      if (router.settings.temperature !== undefined) {
        yamlRouter.settings.temperature = router.settings.temperature;
      }
      if (router.settings.fallback_strategy !== undefined) {
        yamlRouter.settings.fallback_strategy = router.settings.fallback_strategy;
      }
      if (router.settings.analysis_depth !== undefined) {
        yamlRouter.settings.analysis_depth = router.settings.analysis_depth;
      }
      if (router.settings.allow_early_exit !== undefined) {
        yamlRouter.settings.allow_early_exit = router.settings.allow_early_exit;
      }
    }

    return yamlRouter;
  });

  // Build the final YAML structure
  const yamlStructure: any = {
    metadata: {
      name: workflowName || 'Flo AI Workflow',
      version: workflowVersion || '1.0.0',
      description: workflowDescription || 'Generated with Flo AI Studio',
      tags: ['flo-ai', 'studio-generated'],
    },
    arium: {
      agents: yamlAgents,
      tools: tools.length > 0 ? tools.map(name => ({ name })) : undefined,
      routers: yamlRouters.length > 0 ? yamlRouters : undefined,
      workflow: {
        start: finalStartNodeId ? (nodeIdToName.get(finalStartNodeId) || finalStartNodeId) : (agents[0]?.name || ''),
        edges: workflowEdges.filter(edge => edge.to.length > 0),
        end: finalEndNodeIds.map((nodeId) => nodeIdToName.get(nodeId) || nodeId).filter(name => name),
      },
    },
  };

  // Remove undefined fields
  const cleanYamlStructure = JSON.parse(JSON.stringify(yamlStructure, (_, value) => {
    return value === undefined ? null : value;
  }));

  // Remove null values
  function removeNulls(obj: any): any {
    if (Array.isArray(obj)) {
      return obj.map(removeNulls).filter(item => item !== null);
    } else if (obj !== null && typeof obj === 'object') {
      const cleaned: any = {};
      for (const [key, value] of Object.entries(obj)) {
        const cleanValue = removeNulls(value);
        if (cleanValue !== null && cleanValue !== undefined) {
          cleaned[key] = cleanValue;
        }
      }
      return cleaned;
    }
    return obj;
  }

  const finalStructure = removeNulls(cleanYamlStructure);

  return dump(finalStructure, {
    indent: 2,
    lineWidth: 100,
    noRefs: true,
    sortKeys: false,
  });
}

export function downloadYAML(content: string, filename: string = 'flo-ai-workflow.yaml'): void {
  const blob = new Blob([content], { type: 'text/yaml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  URL.revokeObjectURL(url);
}

export function copyToClipboard(content: string): Promise<void> {
  return navigator.clipboard.writeText(content);
}
