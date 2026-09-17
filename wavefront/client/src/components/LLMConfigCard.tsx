import { InferenceEngineType, LLMInferenceConfig } from '@app/types/llm-inference-config';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface LLMConfigCardProps {
  config: LLMInferenceConfig;
  onClick: (configId: string) => void;
  onDeleteClick: (e: React.MouseEvent, config: LLMInferenceConfig) => void;
}

const getTypeColor = (type: InferenceEngineType) => {
  const colors: Record<InferenceEngineType, string> = {
    openai: 'text-emerald-800 bg-emerald-400/15 ring-1 ring-emerald-400/20',
    anthropic: 'text-amber-800 bg-amber-400/15 ring-1 ring-amber-400/20',
    gemini: 'text-sky-800 bg-sky-400/15 ring-1 ring-sky-400/20',
    ollama: 'text-indigo-800 bg-indigo-400/15 ring-1 ring-indigo-400/20',
    vllm: 'text-rose-800 bg-rose-400/15 ring-1 ring-rose-400/20',
    azure_openai: 'text-cyan-800 bg-cyan-400/15 ring-1 ring-cyan-400/20',
    groq: 'text-pink-800 bg-pink-400/15 ring-1 ring-pink-400/20',
  };
  return colors[type] || 'frost-text bg-frost-glass-strong ring-1 ring-frost-border';
};

const LLMConfigCard: React.FC<LLMConfigCardProps> = ({ config, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Id',
      value: config.id,
      isMono: true,
    },
    {
      label: 'Type',
      value: config.type,
      className: `capitalize ${getTypeColor(config.type)}`,
    },
  ];

  if (config.base_url) {
    metadata.push({
      label: 'Base url',
      value: config.base_url,
      className: 'max-w-32 truncate frost-text-muted bg-frost-glass-strong ring-1 ring-frost-border',
    });
  }

  if (config.created_at) {
    metadata.push({
      label: 'Created',
      value: new Date(config.created_at).toLocaleDateString(),
      className: 'frost-text-muted bg-frost-glass-strong ring-1 ring-frost-border',
    });
  }

  return (
    <ResourceCard
      title={config.display_name}
      description={config.llm_model}
      metadata={metadata}
      onClick={() => onClick(config.id)}
      onDeleteClick={(e) => onDeleteClick(e, config)}
      deleteTitle="Delete LLM"
    />
  );
};

export default LLMConfigCard;
