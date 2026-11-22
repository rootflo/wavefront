import { Spinner } from '@app/components/ui/spinner';
import React, { Suspense } from 'react';

// Loaded on demand so React Flow, its CSS and dagre stay out of the workflows page bundle.
const WorkflowVisualEditor = React.lazy(() =>
  import('@app/components/WorkflowBuilder/WorkflowVisualEditor').then((module) => ({
    default: module.WorkflowVisualEditor,
  }))
);

const LazyWorkflowVisualEditor: React.FC<React.ComponentProps<typeof WorkflowVisualEditor>> = (props) => (
  <Suspense
    fallback={
      <div className="flex h-full w-full items-center justify-center">
        <Spinner className="size-6" />
      </div>
    }
  >
    <WorkflowVisualEditor {...props} />
  </Suspense>
);

export default LazyWorkflowVisualEditor;
