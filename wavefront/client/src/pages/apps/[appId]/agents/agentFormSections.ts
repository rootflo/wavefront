import type { AgentFormSection } from './AgentFormFields';

/** Which tab renders each form field, so a failed save can open the tab that has the invalid one. */
export const SECTION_OF_FIELD: Record<string, AgentFormSection> = {
  agentId: 'identity',
  namespace: 'identity',
  agentName: 'identity',
  role: 'identity',
  actAs: 'identity',
  description: 'identity',
  tags: 'identity',
  job: 'identity',
  modelId: 'model',
  temperature: 'advanced',
  reasoningPattern: 'advanced',
  maxTokens: 'advanced',
  topK: 'advanced',
  topP: 'advanced',
  frequencyPenalty: 'advanced',
  presencePenalty: 'advanced',
  seed: 'advanced',
};
