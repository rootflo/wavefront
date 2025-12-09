import { AgentListItem } from '@app/types/agent';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface AgentCardProps {
  agent: AgentListItem;
  onClick: (agentId: string) => void;
  onDeleteClick: (e: React.MouseEvent, agent: AgentListItem) => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Name',
      value: agent.name,
      isMono: true,
    },
    {
      label: 'Namespace',
      value: agent.namespace,
      className: 'bg-blue-50 text-blue-700',
    },
  ];

  return (
    <ResourceCard
      title={agent.name}
      metadata={metadata}
      onClick={() => onClick(agent.id)}
      onDeleteClick={(e) => onDeleteClick(e, agent)}
      deleteTitle="Delete agent"
    />
  );
};

export default AgentCard;
