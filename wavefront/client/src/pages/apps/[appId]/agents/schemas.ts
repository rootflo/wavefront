import { z } from 'zod';

export const createAgentSchema = z.object({
  agentId: z.string().min(1, 'Agent ID is required'),
  namespace: z.string().min(1, 'Namespace is required'),
  yamlContent: z.string().min(1, 'YAML configuration is required'),

  // Identity & Metadata
  agentName: z.string().optional(),
  role: z.string().optional(),
  job: z.string().optional(),
  description: z.string().optional(),
  version: z.string().optional(),
  author: z.string().optional(),
  tags: z.string().optional(), // Comma separated for simplicity in form
  actAs: z.string().optional(),

  // Model Config
  provider: z.string().optional(),
  modelName: z.string().optional(),
  modelId: z.string().optional(),
  baseUrl: z.string().optional(),
  project: z.string().optional(),
  location: z.string().optional(),
  apiKey: z.string().optional(),
  azureEndpoint: z.string().optional(),
  azureApiVersion: z.string().optional(),
  timeout: z.coerce.number().optional().nullable(),

  // Settings
  temperature: z.number().min(0).max(2).optional(),
  maxTokens: z.coerce.number().optional().nullable(),
  maxRetries: z.coerce.number().optional().nullable(),
  reasoningPattern: z.string().optional(),
  topP: z.coerce.number().min(0).max(1).optional().nullable(),
  topK: z.coerce.number().optional().nullable(),
  frequencyPenalty: z.coerce.number().min(-2).max(2).optional().nullable(),
  presencePenalty: z.coerce.number().min(-2).max(2).optional().nullable(),
  seed: z.coerce.number().optional().nullable(),
});

export type CreateAgentInput = z.infer<typeof createAgentSchema>;
