import { LLMInferenceConfig, InferenceEngineType } from '@app/types/llm-inference-config';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface LLMConfigCardProps {
  config: LLMInferenceConfig;
  onClick: (configId: string) => void;
  onDeleteClick: (e: React.MouseEvent, config: LLMInferenceConfig) => void;
}

const getTypeColor = (type: InferenceEngineType) => {
  const colors: Record<InferenceEngineType, string> = {
    openai: 'text-green-700 bg-green-50',
    anthropic: 'text-orange-700 bg-orange-50',
    gemini: 'text-blue-700 bg-blue-50',
    ollama: 'text-purple-700 bg-purple-50',
    vllm: 'text-red-700 bg-red-50',
    azure_openai: 'text-cyan-700 bg-cyan-50',
    groq: 'text-pink-700 bg-pink-50',
  };
  return colors[type] || 'text-gray-700 bg-gray-50';
};

const LLMConfigCard: React.FC<LLMConfigCardProps> = ({ config, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'ID',
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
      label: 'Base URL',
      value: config.base_url,
      className: 'truncate max-w-32 text-gray-600',
    });
  }

  if (config.created_at) {
    metadata.push({
      label: 'Created',
      value: new Date(config.created_at).toLocaleDateString(),
      className: 'text-gray-600',
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
