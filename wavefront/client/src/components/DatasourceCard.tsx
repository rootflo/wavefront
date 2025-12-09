import { Datasource } from '@app/types/datasource';
import dayjs from 'dayjs';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface DatasourceCardProps {
  datasource: Datasource;
  onClick: (datasourceId: string) => void;
  onDeleteClick: (e: React.MouseEvent, datasource: Datasource) => void;
}

const getTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    database: 'text-blue-700 bg-blue-50',
    api: 'text-purple-700 bg-purple-50',
    file: 'text-green-700 bg-green-50',
    cloud: 'text-orange-700 bg-orange-50',
  };
  return colors[type.toLowerCase()] || 'text-gray-700 bg-gray-50';
};

const DatasourceCard: React.FC<DatasourceCardProps> = ({ datasource, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'ID',
      value: datasource.id,
      isMono: true,
    },
    {
      label: 'Type',
      value: datasource.type,
      className: `capitalize ${getTypeColor(datasource.type)}`,
    },
  ];

  if (datasource.created_at) {
    metadata.push({
      label: 'Created',
      value: dayjs(datasource.created_at).format('DD/MM/YYYY HH:mm'),
    });
  }

  return (
    <ResourceCard
      title={datasource.name}
      description={datasource.description || 'No description available'}
      metadata={metadata}
      onClick={() => onClick(datasource.id)}
      onDeleteClick={(e) => onDeleteClick(e, datasource)}
      deleteTitle="Delete datasource"
    />
  );
};

export default DatasourceCard;
