import { Bot } from 'lucide-react';
import { AgentListItem } from '@app/types/agent';
import dayjs from 'dayjs';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from '@app/components/ResourceCard';

interface AgentCardProps {
  agent: AgentListItem;
  onClick: (agentId: string) => void;
  onDeleteClick: (e: React.MouseEvent, agent: AgentListItem) => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Id',
      value: agent.id,
      isMono: true,
      isCopyable: true,
    },
    {
      label: 'Namespace',
      value: agent.namespace,
      className: 'bg-sky-400/15 text-sky-800 dark:text-sky-300 ring-1 ring-sky-400/20',
    },
  ];

  if (agent.current_version !== undefined) {
    metadata.push({
      label: 'Version',
      value: `v${agent.current_version}`,
      className: 'bg-indigo-400/15 text-indigo-800 dark:text-indigo-300 ring-1 ring-indigo-400/20',
    });
  }

  if (agent.updated_at) {
    metadata.push({
      label: 'Updated',
      value: dayjs(agent.updated_at).format('DD MMM YYYY'),
    });
  }

  return (
    <ResourceCard
      icon={Bot}
      title={agent.name}
      metadata={metadata}
      onClick={() => onClick(agent.id)}
      onDeleteClick={(e) => onDeleteClick(e, agent)}
      deleteTitle="Delete agent"
    />
  );
};

export default AgentCard;
