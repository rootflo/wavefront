import { Edge, Node } from '@xyflow/react';
import { NODE_TYPES } from '@app/constants/workflow-builder';

export interface WorkflowTemplate {
  nodes: Node[];
  edges: Edge[];
}

// Factories return fresh objects on every call because auto-layout mutates node positions in place

// Template: Linear (Content Creator -> Editor)
export const createLinearTemplate = (): WorkflowTemplate => {
  const templateNodes: Node[] = [
    {
      id: 'trigger-start',
      type: NODE_TYPES.TRIGGER,
      position: { x: 50, y: 150 },
      data: { label: 'Workflow Trigger', description: 'Triggers the linear flow.', type: 'trigger' },
    },
    {
      id: 'content_creator',
      type: NODE_TYPES.AGENT,
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
      type: NODE_TYPES.AGENT,
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

  return { nodes: templateNodes, edges: templateEdges };
};

// Template: Router (Triage -> Intent Router -> 2 Specialists)
export const createRouterTemplate = (): WorkflowTemplate => {
  const templateNodes: Node[] = [
    {
      id: 'trigger-start',
      type: NODE_TYPES.TRIGGER,
      position: { x: 50, y: 150 },
      data: { label: 'Workflow Trigger', description: 'Triggers request triage.', type: 'trigger' },
    },
    {
      id: 'triage_agent',
      type: NODE_TYPES.AGENT,
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
      type: NODE_TYPES.ROUTER,
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
      type: NODE_TYPES.AGENT,
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
      type: NODE_TYPES.AGENT,
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

  return { nodes: templateNodes, edges: templateEdges };
};
