import { matchPath } from 'react-router';

// Authenticated pages that open in their own browser tab, outside the dashboard layout
export const WORKFLOW_EDITOR_NEW_PATH = '/apps/:app/workflows/new';
export const WORKFLOW_EDITOR_PATH = '/apps/:app/workflows/:id/editor';

const STANDALONE_PATHS = [WORKFLOW_EDITOR_NEW_PATH, WORKFLOW_EDITOR_PATH];

export const isStandalonePath = (pathname: string) => STANDALONE_PATHS.some((path) => matchPath(path, pathname));
