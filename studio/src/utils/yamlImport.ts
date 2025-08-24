import { load } from 'js-yaml';
import { Agent, Router, AriumWorkflow } from '@/types/agent';
import { CustomNode, CustomEdge } from '@/types/reactflow';

export interface ImportResult {
  nodes: CustomNode[];
  edges: CustomEdge[];
  workflowName: string;
  workflowDescription: string;
  workflowVersion: string;
}

export function parseAriumYAML(yamlContent: string): ImportResult {
  try {
    const workflow = load(yamlContent) as AriumWorkflow;
    
    if (!workflow || !workflow.arium) {
      throw new Error('Invalid Arium workflow format');
    }

    const nodes: CustomNode[] = [];
    const edges: CustomEdge[] = [];
    
    // Create agent nodes
    if (workflow.arium.agents) {
      workflow.arium.agents.forEach((agent, index) => {
        const agentNode: CustomNode = {
          id: agent.name,
          type: 'agent',
          position: { 
            x: 100 + (index % 3) * 300, 
            y: 100 + Math.floor(index / 3) * 200 
          },
          data: {
            agent: {
              id: agent.name,
              name: agent.name,
              role: agent.role,
              job: agent.job,
              model: agent.model,
              settings: agent.settings,
              tools: agent.tools,
              parser: agent.parser,
            } as Agent,
          },
        };
        nodes.push(agentNode);
      });
    }

    // Create router nodes if routers are defined
    if (workflow.arium.routers) {
      workflow.arium.routers.forEach((router: any, index: number) => {
        const routerNode: CustomNode = {
          id: router.name,
          type: 'router',
          position: { 
            x: 150 + (index % 3) * 300, 
            y: 300 + Math.floor(index / 3) * 200 
          },
          data: {
            router: {
              id: router.name,
              name: router.name,
              description: router.description || '',
              type: router.type || 'smart',
              model: router.model,
              settings: router.settings,
              routing_options: router.routing_options,
              task_categories: router.task_categories,
              flow_pattern: router.flow_pattern,
            } as Router,
          },
        };
        nodes.push(routerNode);
      });
    }

    // Create tool nodes if tools are defined
    if (workflow.arium.tools) {
      workflow.arium.tools.forEach((tool, index) => {
        const toolNode: CustomNode = {
          id: `tool_${tool.name}`,
          type: 'tool',
          position: { 
            x: 200 + (index % 3) * 300, 
            y: 450 + Math.floor(index / 3) * 200 
          },
          data: {
            tool: {
              name: tool.name,
              description: tool.description || '',
            },
          },
        };
        nodes.push(toolNode);
      });
    }

    // Create edges from workflow definition
    if (workflow.arium.workflow && workflow.arium.workflow.edges) {
      workflow.arium.workflow.edges.forEach((edge, index) => {
        edge.to.forEach((target, targetIndex) => {
          const edgeId = `edge_${edge.from}_${target}_${index}_${targetIndex}`;
          const workflowEdge: CustomEdge = {
            id: edgeId,
            source: edge.from,
            target: target,
            type: 'custom',
            data: {
              router: edge.router,
            },
          };
          edges.push(workflowEdge);
        });
      });
    }

    return {
      nodes,
      edges,
      workflowName: workflow.metadata?.name || 'Imported Workflow',
      workflowDescription: workflow.metadata?.description || '',
      workflowVersion: workflow.metadata?.version || '1.0.0',
    };
  } catch (error) {
    console.error('Error parsing YAML:', error);
    throw new Error(`Failed to parse YAML: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

export function validateAriumYAML(yamlContent: string): { isValid: boolean; error?: string } {
  try {
    const workflow = load(yamlContent) as any;
    
    if (!workflow) {
      return { isValid: false, error: 'Empty or invalid YAML content' };
    }

    if (!workflow.arium) {
      return { isValid: false, error: 'Missing "arium" section in YAML' };
    }

    if (!workflow.arium.agents || !Array.isArray(workflow.arium.agents)) {
      return { isValid: false, error: 'Missing or invalid "agents" array in arium section' };
    }

    // Validate each agent has required fields
    for (const agent of workflow.arium.agents) {
      if (!agent.name) {
        return { isValid: false, error: 'Agent missing required "name" field' };
      }
      if (!agent.job) {
        return { isValid: false, error: `Agent "${agent.name}" missing required "job" field` };
      }
      if (!agent.model || !agent.model.provider || !agent.model.name) {
        return { isValid: false, error: `Agent "${agent.name}" missing required model configuration` };
      }
    }

    // Validate workflow structure if present
    if (workflow.arium.workflow) {
      if (!workflow.arium.workflow.start) {
        return { isValid: false, error: 'Workflow missing "start" node' };
      }
      if (!workflow.arium.workflow.end || !Array.isArray(workflow.arium.workflow.end)) {
        return { isValid: false, error: 'Workflow missing "end" nodes array' };
      }
    }

    return { isValid: true };
  } catch (error) {
    return { 
      isValid: false, 
      error: `YAML parsing error: ${error instanceof Error ? error.message : 'Unknown error'}` 
    };
  }
}

export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      if (event.target?.result) {
        resolve(event.target.result as string);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = () => reject(new Error('File reading error'));
    reader.readAsText(file);
  });
}
