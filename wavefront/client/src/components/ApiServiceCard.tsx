import { ApiServiceItem } from '@app/types/api-service';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface ApiServiceCardProps {
  service: ApiServiceItem;
  onClick: (serviceId: string) => void;
  onDeleteClick: (e: React.MouseEvent, service: ApiServiceItem) => void;
}

const ApiServiceCard: React.FC<ApiServiceCardProps> = ({ service, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Id',
      value: service.service_id,
      isMono: true,
    },
  ];

  if (service.version) {
    metadata.push({
      label: 'Version',
      value: service.version,
      className: 'bg-sky-400/15 text-sky-800 ring-1 ring-sky-400/20',
    });
  }

  return (
    <ResourceCard
      title={service.name || service.service_id}
      description={service.description}
      metadata={metadata}
      onClick={() => onClick(service.service_id)}
      onDeleteClick={(e) => onDeleteClick(e, service)}
      deleteTitle="Delete service"
    />
  );
};

export default ApiServiceCard;
