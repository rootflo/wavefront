import { Datasource } from '@app/types/datasource';
import dayjs from 'dayjs';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface DatasourceCardProps {
  datasource: Datasource;
  onClick: (datasourceId: string) => void;
  onDeleteClick: (e: React.MouseEvent, datasource: Datasource) => void;
}

/** Short chip labels for datasource types. */
const DATASOURCE_TYPE_CHIPS: Record<string, { label: string; className: string }> = {
  gcp_bigquery: {
    label: 'BigQuery',
    className: 'text-sky-800 bg-sky-400/15 ring-1 ring-sky-400/20 dark:text-sky-300',
  },
  aws_redshift: {
    label: 'Redshift',
    className: 'text-violet-800 bg-violet-400/15 ring-1 ring-violet-400/20 dark:text-violet-300',
  },
  postgres: {
    label: 'PostgreSQL',
    className: 'text-indigo-800 bg-indigo-400/15 ring-1 ring-indigo-400/20 dark:text-indigo-300',
  },
  mssql: {
    label: 'MSSQL',
    className: 'text-amber-800 bg-amber-400/15 ring-1 ring-amber-400/20 dark:text-amber-300',
  },
};

const getTypeChip = (type: string) =>
  DATASOURCE_TYPE_CHIPS[type] || {
    label: type,
    className: 'frost-text bg-frost-glass-strong ring-1 ring-frost-border',
  };

const DatasourceCard: React.FC<DatasourceCardProps> = ({ datasource, onClick, onDeleteClick }) => {
  const typeChip = getTypeChip(datasource.type);

  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Id',
      value: datasource.id,
      isMono: true,
      isCopyable: true,
    },
    {
      label: 'Type',
      value: typeChip.label,
      className: typeChip.className,
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
