import { BookOpen } from 'lucide-react';
import { KbData } from '@app/types/knowledge-base';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from '@app/components/ResourceCard';

interface KnowledgeBaseCardProps {
  kb: KbData;
  onClick: (kbId: string) => void;
  onDeleteClick: (e: React.MouseEvent, kb: KbData) => void;
  onEditClick?: (e: React.MouseEvent, kb: KbData) => void;
}

const KnowledgeBaseCard: React.FC<KnowledgeBaseCardProps> = ({ kb, onClick, onDeleteClick, onEditClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Knowledge base id',
      value: kb.id,
      isMono: true,
      isCopyable: true,
    },
  ];

  return (
    <ResourceCard
      icon={BookOpen}
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
