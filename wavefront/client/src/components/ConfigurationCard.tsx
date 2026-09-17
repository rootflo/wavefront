import { ConfigurationListItem } from '@app/types/configuration';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface ConfigurationCardProps {
  configuration: ConfigurationListItem;
  onClick: (configuration: ConfigurationListItem) => void;
  onDeleteClick: (e: React.MouseEvent, configuration: ConfigurationListItem) => void;
}

const ConfigurationCard: React.FC<ConfigurationCardProps> = ({ configuration, onClick, onDeleteClick }) => {
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
