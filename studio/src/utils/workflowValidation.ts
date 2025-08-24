import { CustomNode, CustomEdge } from '@/types/reactflow';

export interface ValidationIssue {
  id: string;
  type: 'error' | 'warning' | 'info';
  message: string;
  nodeId?: string;
  edgeId?: string;
  category: 'structure' | 'configuration' | 'connectivity' | 'best_practice';
}

export interface ValidationResult {
  isValid: boolean;
  issues: ValidationIssue[];
  warnings: ValidationIssue[];
  suggestions: ValidationIssue[];
}

export function validateWorkflow(nodes: CustomNode[], edges: CustomEdge[]): ValidationResult {
  const issues: ValidationIssue[] = [];
  const warnings: ValidationIssue[] = [];
  const suggestions: ValidationIssue[] = [];

  // Check if workflow has any nodes
  if (nodes.length === 0) {
    issues.push({
      id: 'no_nodes',
      type: 'error',
      message: 'Workflow must contain at least one agent',
      category: 'structure',
    });
    return { isValid: false, issues, warnings, suggestions };
  }

  // Validate individual nodes
  for (const node of nodes) {
    if (node.type === 'agent') {
      const agent = (node.data as any).agent;
      
      // Check required fields
      if (!agent.name) {
        issues.push({
          id: `agent_no_name_${node.id}`,
          type: 'error',
          message: 'Agent must have a name',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      if (!agent.job) {
        issues.push({
          id: `agent_no_job_${node.id}`,
          type: 'error',
          message: 'Agent must have a job description',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      if (!agent.model || !agent.model.provider || !agent.model.name) {
        issues.push({
          id: `agent_no_model_${node.id}`,
          type: 'error',
          message: 'Agent must have a valid LLM model configuration',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      // Suggestions for best practices
      if (agent.job && agent.job.length < 20) {
        suggestions.push({
          id: `agent_short_job_${node.id}`,
          type: 'info',
          message: 'Consider providing a more detailed job description for better agent performance',
          nodeId: node.id,
          category: 'best_practice',
        });
      }

      if (agent.settings?.temperature && (agent.settings.temperature < 0 || agent.settings.temperature > 2)) {
        warnings.push({
          id: `agent_temperature_range_${node.id}`,
          type: 'warning',
          message: 'Temperature should be between 0 and 2 for optimal results',
          nodeId: node.id,
          category: 'configuration',
        });
      }
    } else if (node.type === 'router') {
      const router = (node.data as any).router;
      
      if (!router.name) {
        issues.push({
          id: `router_no_name_${node.id}`,
          type: 'error',
          message: 'Router must have a name',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      if (!router.description) {
        warnings.push({
          id: `router_no_description_${node.id}`,
          type: 'warning',
          message: 'Router should have a description explaining its routing logic',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      // Validate router-specific configurations
      if (router.type === 'reflection' && (!router.flow_pattern || router.flow_pattern.length < 2)) {
        issues.push({
          id: `reflection_no_pattern_${node.id}`,
          type: 'error',
          message: 'Reflection router must have a flow pattern with at least 2 agents',
          nodeId: node.id,
          category: 'configuration',
        });
      }

      if (router.type === 'task_classifier' && (!router.task_categories || Object.keys(router.task_categories).length === 0)) {
        issues.push({
          id: `classifier_no_categories_${node.id}`,
          type: 'error',
          message: 'Task classifier router must have at least one task category',
          nodeId: node.id,
          category: 'configuration',
        });
      }
    }
  }

  // Validate workflow structure
  const { startNodes, endNodes, isolatedNodes } = analyzeWorkflowStructure(nodes, edges);

  // Check for start nodes
  if (startNodes.length === 0 && nodes.length > 0) {
    warnings.push({
      id: 'no_start_nodes',
      type: 'warning',
      message: 'Workflow has no clear starting point (nodes with no incoming connections)',
      category: 'structure',
    });
  }

  if (startNodes.length > 1) {
    suggestions.push({
      id: 'multiple_start_nodes',
      type: 'info',
      message: `Workflow has ${startNodes.length} potential starting points. Consider using a single entry point.`,
      category: 'structure',
    });
  }

  // Check for end nodes
  if (endNodes.length === 0 && nodes.length > 0) {
    warnings.push({
      id: 'no_end_nodes',
      type: 'warning',
      message: 'Workflow has no clear ending points (nodes with no outgoing connections)',
      category: 'structure',
    });
  }

  // Check for isolated nodes
  for (const nodeId of isolatedNodes) {
    warnings.push({
      id: `isolated_node_${nodeId}`,
      type: 'warning',
      message: 'This node is not connected to the workflow',
      nodeId,
      category: 'connectivity',
    });
  }

  // Validate edge configurations
  for (const edge of edges) {
    const sourceNode = nodes.find(n => n.id === edge.source);
    const targetNode = nodes.find(n => n.id === edge.target);

    if (!sourceNode || !targetNode) {
      issues.push({
        id: `invalid_edge_${edge.id}`,
        type: 'error',
        message: 'Edge connects to non-existent nodes',
        edgeId: edge.id,
        category: 'connectivity',
      });
      continue;
    }

    // Check if edge has a router configuration when connecting to multiple targets
    const outgoingEdges = edges.filter(e => e.source === edge.source);
    if (outgoingEdges.length > 1 && !edge.data?.router) {
      suggestions.push({
        id: `multiple_outputs_no_router_${edge.id}`,
        type: 'info',
        message: 'Consider adding a router for nodes with multiple output connections',
        edgeId: edge.id,
        category: 'best_practice',
      });
    }
  }

  // Check for potential cycles
  const cycles = detectCycles(nodes, edges);
  for (const cycle of cycles) {
    if (cycle.length > 0) {
      warnings.push({
        id: `cycle_detected_${cycle.join('_')}`,
        type: 'warning',
        message: `Potential infinite loop detected involving nodes: ${cycle.join(' → ')}`,
        category: 'structure',
      });
    }
  }

  const isValid = issues.length === 0;
  return { isValid, issues, warnings, suggestions };
}

function analyzeWorkflowStructure(nodes: CustomNode[], edges: CustomEdge[]) {
  const nodeConnections = new Map<string, { incoming: string[], outgoing: string[] }>();
  
  // Initialize connections map
  nodes.forEach(node => {
    nodeConnections.set(node.id, { incoming: [], outgoing: [] });
  });

  // Build connections
  edges.forEach(edge => {
    const sourceConnections = nodeConnections.get(edge.source);
    const targetConnections = nodeConnections.get(edge.target);
    
    if (sourceConnections) {
      sourceConnections.outgoing.push(edge.target);
    }
    if (targetConnections) {
      targetConnections.incoming.push(edge.source);
    }
  });

  // Find start nodes (no incoming connections)
  const startNodes = nodes
    .filter(node => {
      const connections = nodeConnections.get(node.id);
      return connections && connections.incoming.length === 0;
    })
    .map(node => node.id);

  // Find end nodes (no outgoing connections)
  const endNodes = nodes
    .filter(node => {
      const connections = nodeConnections.get(node.id);
      return connections && connections.outgoing.length === 0;
    })
    .map(node => node.id);

  // Find isolated nodes (no connections at all)
  const isolatedNodes = nodes
    .filter(node => {
      const connections = nodeConnections.get(node.id);
      return connections && connections.incoming.length === 0 && connections.outgoing.length === 0;
    })
    .map(node => node.id);

  return { startNodes, endNodes, isolatedNodes };
}

function detectCycles(nodes: CustomNode[], edges: CustomEdge[]): string[][] {
  const cycles: string[][] = [];
  const visited = new Set<string>();
  const recursionStack = new Set<string>();
  const nodeMap = new Map<string, string[]>();

  // Build adjacency list
  nodes.forEach(node => nodeMap.set(node.id, []));
  edges.forEach(edge => {
    const targets = nodeMap.get(edge.source) || [];
    targets.push(edge.target);
    nodeMap.set(edge.source, targets);
  });

  function dfs(nodeId: string, path: string[]): boolean {
    visited.add(nodeId);
    recursionStack.add(nodeId);
    path.push(nodeId);

    const neighbors = nodeMap.get(nodeId) || [];
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        if (dfs(neighbor, [...path])) {
          return true;
        }
      } else if (recursionStack.has(neighbor)) {
        // Found a cycle
        const cycleStart = path.indexOf(neighbor);
        if (cycleStart !== -1) {
          cycles.push(path.slice(cycleStart));
        }
        return true;
      }
    }

    recursionStack.delete(nodeId);
    return false;
  }

  // Check for cycles starting from each unvisited node
  for (const node of nodes) {
    if (!visited.has(node.id)) {
      dfs(node.id, []);
    }
  }

  return cycles;
}

export function getValidationSummary(result: ValidationResult): string {
  const { issues, warnings, suggestions } = result;
  
  if (issues.length === 0 && warnings.length === 0) {
    return `✅ Workflow is valid! ${suggestions.length > 0 ? `${suggestions.length} suggestions available.` : ''}`;
  }
  
  const parts = [];
  if (issues.length > 0) {
    parts.push(`${issues.length} error${issues.length === 1 ? '' : 's'}`);
  }
  if (warnings.length > 0) {
    parts.push(`${warnings.length} warning${warnings.length === 1 ? '' : 's'}`);
  }
  
  return `⚠️ ${parts.join(', ')} found in workflow`;
}
