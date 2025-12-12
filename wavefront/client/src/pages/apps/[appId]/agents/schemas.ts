import { z } from 'zod';

export const createAgentSchema = z.object({
  agentId: z.string().min(1, 'Agent ID is required'),
  namespace: z.string().min(1, 'Namespace is required'),
  yamlContent: z.string().min(1, 'YAML configuration is required'),
});

export type CreateAgentInput = z.infer<typeof createAgentSchema>;
