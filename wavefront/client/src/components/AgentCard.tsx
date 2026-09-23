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
      className: 'bg-sky-400/15 text-sky-800 ring-1 ring-sky-400/20',
    },
  ];

  if (agent.current_version !== undefined) {
    metadata.push({
      label: 'Version',
      value: `v${agent.current_version}`,
      className: 'bg-indigo-400/15 text-indigo-800 ring-1 ring-indigo-400/20',
    });
  }

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
