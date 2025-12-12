import { WorkflowPipelineListItem } from '@app/types/workflow';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';
import dayjs from 'dayjs';

interface WorkflowPipelineCardNewProps {
  pipeline: WorkflowPipelineListItem;
  onClick: (pipelineId: string) => void;
  onDeleteClick: (e: React.MouseEvent, pipeline: WorkflowPipelineListItem) => void;
}

const WorkflowPipelineCardNew: React.FC<WorkflowPipelineCardNewProps> = ({ pipeline, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Pipeline ID',
      value: pipeline.id,
      isMono: true,
    },
    {
      label: 'Location',
      value: pipeline.location,
      className: 'bg-blue-50 text-blue-700',
    },
    {
      label: 'Concurrency Limit',
      value: pipeline.concurrency_limit.toString(),
      className: 'bg-green-50 text-green-700',
    },
  ];

  if (pipeline.timeout) {
    metadata.push({
      label: 'Timeout',
      value: pipeline.timeout,
      className: 'bg-yellow-50 text-yellow-700',
    });
  }

  metadata.push({
    label: 'Created',
    value: dayjs(pipeline.created_at).format('DD MMM YYYY hh:mm A'),
  });

  return (
    <ResourceCard
      title={pipeline.name}
      description={pipeline.description || 'No description available'}
      metadata={metadata}
      onClick={() => onClick(pipeline.id)}
      onDeleteClick={(e) => onDeleteClick(e, pipeline)}
      deleteTitle="Delete workflow pipeline"
    />
  );
};

export default WorkflowPipelineCardNew;
