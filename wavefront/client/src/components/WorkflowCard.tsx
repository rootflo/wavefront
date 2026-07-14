import { WorkflowListItem } from '@app/types/workflow';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface WorkflowCardNewProps {
  workflow: WorkflowListItem;
  onClick: (workflowId: string) => void;
  onDeleteClick: (e: React.MouseEvent, workflow: WorkflowListItem) => void;
}

const WorkflowCardNew: React.FC<WorkflowCardNewProps> = ({ workflow, onClick, onDeleteClick }) => {
  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Namespace',
      value: workflow.namespace,
      className: 'bg-blue-50 text-blue-700',
    },
    {
      label: 'ID',
      value: workflow.id,
      isMono: true,
    },
  ];

  if (workflow.current_version !== undefined) {
    metadata.push({
      label: 'Version',
      value: `v${workflow.current_version}`,
      className: 'bg-purple-50 text-purple-700',
    });
  }

  return (
    <ResourceCard
      title={workflow.name}
      metadata={metadata}
      onClick={() => onClick(workflow.id)}
      onDeleteClick={(e) => onDeleteClick(e, workflow)}
      deleteTitle="Delete workflow"
    />
  );
};

export default WorkflowCardNew;
