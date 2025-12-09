import { ModelData } from '@app/api/model-inference-service';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface ModelCardProps {
  model: ModelData;
  onClick: (modelId: string) => void;
  onDeleteClick: (e: React.MouseEvent, model: ModelData) => void;
}

const ModelCard: React.FC<ModelCardProps> = ({ model, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Model ID',
      value: model.model_id,
      isMono: true,
    },
    {
      label: 'Type',
      value: model.model_type,
      className: 'bg-blue-50 text-blue-700',
    },
  ];

  return (
    <ResourceCard
      title={model.model_name || model.model_id}
      description={`Type: ${model.model_type}`}
      metadata={metadata}
      onClick={() => onClick(model.model_id)}
      onDeleteClick={(e) => onDeleteClick(e, model)}
      deleteTitle="Delete model"
    />
  );
};

export default ModelCard;
