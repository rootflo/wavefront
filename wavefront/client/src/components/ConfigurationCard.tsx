import { ConfigurationListItem } from '@app/types/configuration';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface ConfigurationCardProps {
  configuration: ConfigurationListItem;
  onClick: (configuration: ConfigurationListItem) => void;
  onDeleteClick: (e: React.MouseEvent, configuration: ConfigurationListItem) => void;
}

const ConfigurationCard: React.FC<ConfigurationCardProps> = ({ configuration, onClick, onDeleteClick }) => {
  // The key is the title, so the namespace is what distinguishes two configs
  // that share a key — it earns the metadata row ahead of the surrogate id.
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Namespace',
      value: configuration.namespace,
      isMono: true,
    },
  ];

  return (
    <ResourceCard
      title={configuration.key}
      description={configuration.description}
      metadata={metadata}
      onClick={() => onClick(configuration)}
      onDeleteClick={(e) => onDeleteClick(e, configuration)}
      deleteTitle="Delete configuration"
    />
  );
};

export default ConfigurationCard;
