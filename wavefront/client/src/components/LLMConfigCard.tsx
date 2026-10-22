import { Cpu } from 'lucide-react';
import { InferenceEngineType, LLMInferenceConfig } from '@app/types/llm-inference-config';
import React from 'react';
import { LLM_PROVIDERS_CONFIG } from '@app/config/llm-providers';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface LLMConfigCardProps {
  config: LLMInferenceConfig;
  onClick: (configId: string) => void;
  onDeleteClick: (e: React.MouseEvent, config: LLMInferenceConfig) => void;
}

export const getTypeColor = (type: InferenceEngineType) => {
  const colors: Record<InferenceEngineType, string> = {
    openai: 'text-emerald-800 dark:text-emerald-300 bg-emerald-400/15 ring-1 ring-emerald-400/20',
    anthropic: 'text-amber-800 dark:text-amber-300 bg-amber-400/15 ring-1 ring-amber-400/20',
    gemini: 'text-sky-800 dark:text-sky-300 bg-sky-400/15 ring-1 ring-sky-400/20',
    ollama: 'text-indigo-800 dark:text-indigo-300 bg-indigo-400/15 ring-1 ring-indigo-400/20',
    vllm: 'text-rose-800 dark:text-rose-300 bg-rose-400/15 ring-1 ring-rose-400/20',
    azure_openai: 'text-cyan-800 dark:text-cyan-300 bg-cyan-400/15 ring-1 ring-cyan-400/20',
    groq: 'text-pink-800 dark:text-pink-300 bg-pink-400/15 ring-1 ring-pink-400/20',
    bedrock: 'text-orange-800 dark:text-orange-300 bg-orange-400/15 ring-1 ring-orange-400/20',
  };
  return colors[type] || 'frost-text bg-frost-glass-strong ring-1 ring-frost-border';
};

const LLMConfigCard: React.FC<LLMConfigCardProps> = ({ config, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Id',
      value: config.id,
      isMono: true,
      isCopyable: true,
    },
    {
      label: 'Model',
      value: config.llm_model,
      className: 'max-w-32 truncate frost-text-muted bg-frost-glass-strong ring-1 ring-frost-border',
    },
  ];

  return (
    <ResourceCard
      icon={Cpu}
      title={config.display_name}
      metadata={metadata}
      chips={[{ label: LLM_PROVIDERS_CONFIG[config.type]?.name ?? config.type, className: getTypeColor(config.type) }]}
      onClick={() => onClick(config.id)}
      onDeleteClick={(e) => onDeleteClick(e, config)}
      deleteTitle="Delete LLM"
    />
  );
};

export default LLMConfigCard;
