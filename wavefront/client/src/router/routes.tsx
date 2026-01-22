import Dashboard from '@app/pages/apps';
import Agents from '@app/pages/apps/[appId]/agents';
import AgentDetail from '@app/pages/apps/[appId]/agents/[id]';
import ApiServiceManagement from '@app/pages/apps/[appId]/api-services';
import ApiServiceDetail from '@app/pages/apps/[appId]/api-services/[id]';
import AuthenticatorsPage from '@app/pages/apps/[appId]/authenticators';
import AuthenticatorDetailPage from '@app/pages/apps/[appId]/authenticators/[authId]';
import DatasourcesManagement from '@app/pages/apps/[appId]/datasources';
import DatasourceDetail from '@app/pages/apps/[appId]/datasources/[datasourceId]';
import FunctionsManagement from '@app/pages/apps/[appId]/functions';
import FunctionDetail from '@app/pages/apps/[appId]/functions/[functionId]';
import KnowledgeBaseDetailPage from '@app/pages/apps/[appId]/knowledge-bases/[kbId]';
import KnowledgeBasesListPage from '@app/pages/apps/[appId]/knowledge-bases/index';
import LLMInferenceConfigsManagement from '@app/pages/apps/[appId]/llm-inference';
import LLMInferenceConfigDetail from '@app/pages/apps/[appId]/llm-inference/[configId]';
import ModelManagement from '@app/pages/apps/[appId]/model-inference';
import ModelDetail from '@app/pages/apps/[appId]/model-inference/[modelId]';
import VoiceAgentsPage from '@app/pages/apps/[appId]/voice-agents';
import VoiceAgentsLayout from '@app/pages/apps/[appId]/voice-agents/layout';
import SttConfigsPage from '@app/pages/apps/[appId]/voice-agents/stt-configs';
import TelephonyConfigsPage from '@app/pages/apps/[appId]/voice-agents/telephony-configs';
import ToolsPage from '@app/pages/apps/[appId]/voice-agents/tools';
import TtsConfigsPage from '@app/pages/apps/[appId]/voice-agents/tts-configs';
import WorkflowManagement from '@app/pages/apps/[appId]/workflows';
import WorkflowDetail from '@app/pages/apps/[appId]/workflows/[id]';
import WorkflowsLayout from '@app/pages/apps/[appId]/workflows/layout';
import WorkflowPipelinesPage from '@app/pages/apps/[appId]/workflows/pipelines';
import WorkflowPipelineDetail from '@app/pages/apps/[appId]/workflows/pipelines/[workflowPipelineId]';
import UsersPage from '@app/pages/apps/users';
import CreateApp from '@app/pages/apps/create';
import EditApp from '@app/pages/apps/edit/[appId]';
import AppLayout from '@app/pages/apps/layout';
import ForgotPassword from '@app/pages/forgot-password';
import Login from '@app/pages/login';
import Logout from '@app/pages/logout';
import ResetPassword from '@app/pages/reset-password';
import { Navigate } from 'react-router';
// import PipelineManagement from '@app/pages/pipelines';
// import PipelineDetail from '@app/pages/pipelines/[pipelineId]';
// import CreatePipeline from '@app/pages/pipelines/create';

const routes = {
  public: [
    {
      path: '/',
      element: <Navigate to="/login" />,
    },
    {
      path: '/login',
      element: <Login />,
    },
    {
      path: '/forgot-password',
      element: <ForgotPassword />,
    },
    {
      path: '/reset-password',
      element: <ResetPassword />,
    },
  ],
  private: [
    {
      path: '/apps',
      element: <Dashboard />,
    },
    {
      path: '/logout',
      element: <Logout />,
    },
    {
      path: '/apps/users',
      element: <UsersPage />,
    },
    {
      path: 'apps/:app',
      element: <AppLayout />,
      children: [
        {
          path: 'agents',
          element: <Agents />,
        },
        {
          path: 'agents/:id',
          element: <AgentDetail />,
        },
        {
          path: 'api-services',
          element: <ApiServiceManagement />,
        },
        {
          path: 'api-services/:id',
          element: <ApiServiceDetail />,
        },
        {
          path: 'datasources',
          element: <DatasourcesManagement />,
        },
        {
          path: 'datasources/:datasourceId',
          element: <DatasourceDetail />,
        },
        {
          path: 'model-inference',
          element: <ModelManagement />,
        },
        {
          path: 'model-inference/:modelId',
          element: <ModelDetail />,
        },
        {
          path: 'knowledge-bases',
          element: <KnowledgeBasesListPage />,
        },
        {
          path: 'knowledge-bases/:kbId',
          element: <KnowledgeBaseDetailPage />,
        },
        {
          path: 'llm-repository',
          element: <LLMInferenceConfigsManagement />,
        },
        {
          path: 'llm-repository/:llmId',
          element: <LLMInferenceConfigDetail />,
        },
        {
          path: 'workflows',
          element: <WorkflowsLayout />,
          children: [
            {
              index: true,
              element: <WorkflowManagement />,
            },
            {
              path: 'pipelines',
              element: <WorkflowPipelinesPage />,
            },
            {
              path: ':id',
              element: <WorkflowDetail />,
            },
          ],
        },
        {
          path: 'workflows/pipelines/:workflowPipelineId',
          element: <WorkflowPipelineDetail />,
        },
        {
          path: 'functions',
          element: <FunctionsManagement />,
        },
        {
          path: 'functions/:functionId',
          element: <FunctionDetail />,
        },
        // {
        //   path: 'data-pipelines',
        //   element: <PipelineManagement />,
        // },
        // {
        //   path: 'data-pipelines/create',
        //   element: <CreatePipeline />,
        // },
        // {
        //   path: 'data-pipelines/:pipelineId',
        //   element: <PipelineDetail />,
        // },
        {
          path: 'voice-agents',
          element: <VoiceAgentsLayout />,
          children: [
            {
              index: true,
              element: <VoiceAgentsPage />,
            },
            {
              path: 'tools',
              element: <ToolsPage />,
            },
            {
              path: 'tts-configs',
              element: <TtsConfigsPage />,
            },
            {
              path: 'stt-configs',
              element: <SttConfigsPage />,
            },
            {
              path: 'telephony-configs',
              element: <TelephonyConfigsPage />,
            },
          ],
        },
        {
          path: 'authenticators',
          element: <AuthenticatorsPage />,
        },
        {
          path: 'authenticators/:authId',
          element: <AuthenticatorDetailPage />,
        },
      ],
    },
    {
      path: '/apps/create',
      element: <CreateApp />,
    },
    {
      path: '/apps/edit/:appId',
      element: <EditApp />,
    },
  ],
  admin: [],
  manager: [],
};

export default routes;
