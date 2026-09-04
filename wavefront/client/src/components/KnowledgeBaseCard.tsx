import { KbData } from '@app/api/knowledge-base-service';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface KnowledgeBaseCardProps {
  kb: KbData;
  onClick: (kbId: string) => void;
  onDeleteClick: (e: React.MouseEvent, kb: KbData) => void;
  onEditClick?: (e: React.MouseEvent, kb: KbData) => void;
}

const KnowledgeBaseCard: React.FC<KnowledgeBaseCardProps> = ({ kb, onClick, onDeleteClick, onEditClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Knowledge Base ID',
      value: kb.id,
      isMono: true,
    },
  ];

  return (
    <ResourceCard
      title={kb.name}
      description={kb.description || 'No description provided.'}
      metadata={metadata}
      onClick={() => onClick(kb.id)}
      onDeleteClick={(e) => onDeleteClick(e, kb)}
      onEditClick={onEditClick ? (e) => onEditClick(e, kb) : undefined}
      deleteTitle="Delete knowledge base"
      editTitle="Edit knowledge base"
    />
  );
};

export default KnowledgeBaseCard;
