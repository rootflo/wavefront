import { MessageProcessorListItem } from '@app/types/message-processor';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface FunctionCardProps {
  processor: MessageProcessorListItem;
  onClick: (processorId: string) => void;
  onDeleteClick: (e: React.MouseEvent, processor: MessageProcessorListItem) => void;
}

const FunctionCard: React.FC<FunctionCardProps> = ({ processor, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'ID',
      value: processor.id,
      isMono: true,
    },
  ];

  return (
    <ResourceCard
      title={processor.name}
      description={processor.description}
      metadata={metadata}
      onClick={() => onClick(processor.id)}
      onDeleteClick={(e) => onDeleteClick(e, processor)}
      deleteTitle="Delete function"
    />
  );
};

export default FunctionCard;
