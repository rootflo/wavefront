import { DocumentData, InferenceData, KbData } from '@app/api/knowledge-base-service';
import { ModelData } from '@app/api/model-inference-service';
import { NamespaceItem } from '@app/api/namespace-service';
import { useQueryInit } from '@app/lib/react-query';
import { AgentApi, AgentListItem } from '@app/types/agent';
import { ApiServiceItem } from '@app/types/api-service';
import { App } from '@app/types/app';
import { Authenticator } from '@app/types/authenticator';
import { Datasource, ReadYamlData, Yaml } from '@app/types/datasource';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { MessageProcessor, MessageProcessorListItem } from '@app/types/message-processor';
import { Pipeline, PipelineFile, PipelineStatus } from '@app/types/pipeline';
import { SttConfig } from '@app/types/stt-config';
import { TelephonyConfig } from '@app/types/telephony-config';
import { ToolDetails } from '@app/types/tool';
import { TtsConfig } from '@app/types/tts-config';
import { VoiceAgent } from '@app/types/voice-agent';
import { WorkflowListItem, WorkflowPipelineListItem, WorkflowRunListData } from '@app/types/workflow';
import { UseQueryResult } from '@tanstack/react-query';

import { IUser } from '@app/types/user';
import {
  getAgentQueryFn,
  getAgentsQueryFn,
  getAllAppsQueryFn,
  getAllDatasourcesQueryFn,
  getAllYamlsQueryFn,
  getApiServiceQueryFn,
  getApiServicesQueryFn,
  getAppByIdFn,
  getAuthenticatorQueryFn,
  getAuthenticatorsQueryFn,
  getCurrentUserQueryFn,
  getDatasourceQueryFn,
  getDatasourceResourcesQueryFn,
  getKnowledgeBaseDocumentsQueryFn,
  getKnowledgeBaseInferencesQueryFn,
  getKnowledgeBaseQueryFn,
  getKnowledgeBasesQueryFn,
  getLLMConfigQueryFn,
  getLLMConfigsQueryFn,
  getMessageProcessorQueryFn,
  getMessageProcessorsQueryFn,
  getModelQueryFn,
  getModelsQueryFn,
  getNamespacesQueryFn,
  getPipelineFilesQueryFn,
  getPipelineQueryFn,
  getPipelinesQueryFn,
  getSttConfigQueryFn,
  getSttConfigsQueryFn,
  getTelephonyConfigQueryFn,
  getTelephonyConfigsQueryFn,
  getToolsQueryFn,
  getTtsConfigQueryFn,
  getTtsConfigsQueryFn,
  getVoiceAgentQueryFn,
  getVoiceAgentsQueryFn,
  getWorkflowPipelinesQueryFn,
  getWorkflowRunsQueryFn,
  getWorkflowsQueryFn,
  readYamlQueryFn,
} from './query-functions';
import {
  getAgentKey,
  getAgentsKey,
  getAllAppsKey,
  getAllDatasourcesKey,
  getAllYamlsKey,
  getApiServiceKey,
  getApiServicesKey,
  getAppByIdKey,
  getAuthenticatorKey,
  getAuthenticatorsKey,
  getCurrentUserKey,
  getDatasourceKey,
  getDatasourceResourcesKey,
  getKnowledgeBaseDocumentsKey,
  getKnowledgeBaseInferencesKey,
  getKnowledgeBaseKey,
  getKnowledgeBasesKey,
  getLLMConfigKey,
  getLLMConfigsKey,
  getMessageProcessorKey,
  getMessageProcessorsKey,
  getModelKey,
  getModelsKey,
  getNamespacesKey,
  getPipelineFilesKey,
  getPipelineKey,
  getPipelinesKey,
  getSttConfigKey,
  getSttConfigsKey,
  getTelephonyConfigKey,
  getTelephonyConfigsKey,
  getToolsKey,
  getTtsConfigKey,
  getTtsConfigsKey,
  getVoiceAgentKey,
  getVoiceAgentsKey,
  getWorkflowPipelinesKey,
  getWorkflowRunsKey,
  getWorkflowsKey,
  readYamlKey,
} from './query-keys';

export const useGetAllApps = (enabled: boolean): UseQueryResult<App[], Error> => {
  return useQueryInit(getAllAppsKey(), getAllAppsQueryFn, enabled);
};

export const useGetCurrentUser = (enabled: boolean): UseQueryResult<IUser | null, Error> => {
  return useQueryInit(getCurrentUserKey(), getCurrentUserQueryFn, enabled);
};

export const useGetAllDatasources = (appId: string | undefined): UseQueryResult<Datasource[], Error> => {
  return useQueryInit(getAllDatasourcesKey(appId || ''), getAllDatasourcesQueryFn, !!appId);
};

export const useGetDatasource = (
  appId: string | undefined,
  datasourceId: string | undefined
): UseQueryResult<Datasource | null, Error> => {
  return useQueryInit(
    getDatasourceKey(appId || '', datasourceId || ''),
    () => getDatasourceQueryFn(datasourceId!),
    !!appId && !!datasourceId
  );
};

export const useGetAllYamls = (
  appId: string | undefined,
  datasourceId: string | undefined
): UseQueryResult<Yaml[], Error> => {
  return useQueryInit(
    getAllYamlsKey(appId || '', datasourceId || ''),
    () => getAllYamlsQueryFn(datasourceId!),
    !!appId && !!datasourceId
  );
};

export const useReadYaml = (
  appId: string | undefined,
  datasourceId: string | undefined,
  yamlId: string | undefined
): UseQueryResult<ReadYamlData | null, Error> => {
  return useQueryInit(
    readYamlKey(appId || '', datasourceId || '', yamlId || ''),
    () => readYamlQueryFn(datasourceId!, yamlId!),
    !!appId && !!datasourceId && !!yamlId
  );
};

export const useGetDatasourceResources = (
  appId: string | undefined,
  datasourceId: string | undefined
): UseQueryResult<string[], Error> => {
  return useQueryInit(
    getDatasourceResourcesKey(appId || '', datasourceId || ''),
    () => getDatasourceResourcesQueryFn(datasourceId!),
    !!appId && !!datasourceId
  );
};

export const useGetAgents = (appId: string | undefined, namespace?: string): UseQueryResult<AgentListItem[], Error> => {
  return useQueryInit(getAgentsKey(appId || '', namespace), () => getAgentsQueryFn(namespace), !!appId);
};

export const useGetNamespaces = (appId: string | undefined): UseQueryResult<NamespaceItem[], Error> => {
  return useQueryInit(getNamespacesKey(appId || ''), getNamespacesQueryFn, !!appId);
};

export const useGetApiServices = (appId: string | undefined): UseQueryResult<ApiServiceItem[], Error> => {
  return useQueryInit(getApiServicesKey(appId || ''), getApiServicesQueryFn, !!appId);
};

export const useGetAuthenticators = (appId: string | undefined): UseQueryResult<Authenticator[], Error> => {
  return useQueryInit(getAuthenticatorsKey(appId || ''), getAuthenticatorsQueryFn, !!appId);
};

export const useGetAuthenticator = (
  appId: string | undefined,
  authId: string | undefined
): UseQueryResult<Authenticator | null, Error> => {
  return useQueryInit(
    getAuthenticatorKey(appId || '', authId || ''),
    () => getAuthenticatorQueryFn(authId!),
    !!appId && !!authId
  );
};

export const useGetLLMConfigs = (appId: string | undefined): UseQueryResult<LLMInferenceConfig[], Error> => {
  return useQueryInit(getLLMConfigsKey(appId || ''), getLLMConfigsQueryFn, !!appId);
};

export const useGetLLMConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<LLMInferenceConfig | null, Error> => {
  return useQueryInit(
    getLLMConfigKey(appId || '', configId || ''),
    () => getLLMConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

export const useGetModels = (appId: string | undefined): UseQueryResult<ModelData[], Error> => {
  return useQueryInit(getModelsKey(appId || ''), getModelsQueryFn, !!appId);
};

export const useGetModel = (
  appId: string | undefined,
  modelId: string | undefined
): UseQueryResult<ModelData | null, Error> => {
  return useQueryInit(getModelKey(appId || '', modelId || ''), () => getModelQueryFn(modelId!), !!appId && !!modelId);
};

export const useGetKnowledgeBases = (appId: string | undefined): UseQueryResult<KbData[], Error> => {
  return useQueryInit(getKnowledgeBasesKey(appId || ''), getKnowledgeBasesQueryFn, !!appId);
};

export const useGetKnowledgeBase = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<KbData | null, Error> => {
  return useQueryInit(
    getKnowledgeBaseKey(appId || '', kbId || ''),
    () => getKnowledgeBaseQueryFn(kbId!),
    !!appId && !!kbId
  );
};

export const useGetKnowledgeBaseDocuments = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<DocumentData[], Error> => {
  return useQueryInit(
    getKnowledgeBaseDocumentsKey(appId || '', kbId || ''),
    () => getKnowledgeBaseDocumentsQueryFn(kbId!),
    !!appId && !!kbId
  );
};

export const useGetKnowledgeBaseInferences = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<InferenceData[], Error> => {
  return useQueryInit(
    getKnowledgeBaseInferencesKey(appId || '', kbId || ''),
    () => getKnowledgeBaseInferencesQueryFn(kbId!),
    !!appId && !!kbId
  );
};

export const useGetWorkflows = (
  appId: string | undefined,
  namespace?: string
): UseQueryResult<WorkflowListItem[], Error> => {
  return useQueryInit(getWorkflowsKey(appId || '', namespace), () => getWorkflowsQueryFn(namespace), !!appId);
};

export const useGetWorkflowPipelines = (
  appId: string | undefined
): UseQueryResult<WorkflowPipelineListItem[], Error> => {
  return useQueryInit(getWorkflowPipelinesKey(appId || ''), getWorkflowPipelinesQueryFn, !!appId);
};

export const useGetWorkflowRuns = (
  appId: string | undefined,
  workflowPipelineId: string | undefined,
  offset: number = 0,
  limit: number = 10
): UseQueryResult<WorkflowRunListData, Error> => {
  return useQueryInit(
    getWorkflowRunsKey(appId || '', workflowPipelineId || '', offset, limit),
    () => getWorkflowRunsQueryFn(workflowPipelineId!, offset, limit),
    !!appId && !!workflowPipelineId
  );
};

export const useGetVoiceAgents = (appId: string | undefined): UseQueryResult<VoiceAgent[], Error> => {
  return useQueryInit(getVoiceAgentsKey(appId || ''), getVoiceAgentsQueryFn, !!appId);
};

export const useGetTtsConfigs = (appId: string | undefined): UseQueryResult<TtsConfig[], Error> => {
  return useQueryInit(getTtsConfigsKey(appId || ''), getTtsConfigsQueryFn, !!appId);
};

export const useGetSttConfigs = (appId: string | undefined): UseQueryResult<SttConfig[], Error> => {
  return useQueryInit(getSttConfigsKey(appId || ''), getSttConfigsQueryFn, !!appId);
};

export const useGetTelephonyConfigs = (appId: string | undefined): UseQueryResult<TelephonyConfig[], Error> => {
  return useQueryInit(getTelephonyConfigsKey(appId || ''), getTelephonyConfigsQueryFn, !!appId);
};

export const useGetVoiceAgent = (
  appId: string | undefined,
  agentId: string | undefined
): UseQueryResult<VoiceAgent | null, Error> => {
  return useQueryInit(
    getVoiceAgentKey(appId || '', agentId || ''),
    () => getVoiceAgentQueryFn(agentId!),
    !!appId && !!agentId
  );
};

export const useGetTtsConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<TtsConfig | null, Error> => {
  return useQueryInit(
    getTtsConfigKey(appId || '', configId || ''),
    () => getTtsConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

export const useGetSttConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<SttConfig | null, Error> => {
  return useQueryInit(
    getSttConfigKey(appId || '', configId || ''),
    () => getSttConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

export const useGetTelephonyConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<TelephonyConfig | null, Error> => {
  return useQueryInit(
    getTelephonyConfigKey(appId || '', configId || ''),
    () => getTelephonyConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

export const useGetAgent = (
  appId: string | undefined,
  agentId: string | undefined
): UseQueryResult<AgentApi | null, Error> => {
  return useQueryInit(getAgentKey(appId || '', agentId || ''), () => getAgentQueryFn(agentId!), !!appId && !!agentId);
};

export const useGetTools = (appId: string | undefined): UseQueryResult<ToolDetails[], Error> => {
  return useQueryInit(getToolsKey(appId || ''), getToolsQueryFn, !!appId);
};

export const useGetApiService = (
  appId: string | undefined,
  serviceId: string | undefined
): UseQueryResult<ApiServiceItem | null, Error> => {
  return useQueryInit(
    getApiServiceKey(appId || '', serviceId || ''),
    () => getApiServiceQueryFn(serviceId!),
    !!appId && !!serviceId
  );
};

export const useGetMessageProcessors = (
  appId: string | undefined
): UseQueryResult<MessageProcessorListItem[], Error> => {
  return useQueryInit(getMessageProcessorsKey(appId || ''), getMessageProcessorsQueryFn, !!appId);
};

export const useGetMessageProcessor = (
  appId: string | undefined,
  processorId: string | undefined
): UseQueryResult<MessageProcessor | null, Error> => {
  return useQueryInit(
    getMessageProcessorKey(appId || '', processorId || ''),
    () => getMessageProcessorQueryFn(processorId!),
    !!appId && !!processorId
  );
};

export const useGetPipelines = (
  appId: string | undefined,
  statusFilter?: PipelineStatus | 'all'
): UseQueryResult<Pipeline[], Error> => {
  return useQueryInit(getPipelinesKey(appId || '', statusFilter), () => getPipelinesQueryFn(statusFilter), !!appId);
};

export const useGetPipeline = (
  appId: string | undefined,
  pipelineId: string | undefined
): UseQueryResult<Pipeline | null, Error> => {
  return useQueryInit(
    getPipelineKey(appId || '', pipelineId || ''),
    () => getPipelineQueryFn(pipelineId!),
    !!appId && !!pipelineId
  );
};

export const useGetPipelineFiles = (
  appId: string | undefined,
  pipelineId: string | undefined
): UseQueryResult<PipelineFile[], Error> => {
  return useQueryInit(
    getPipelineFilesKey(appId || '', pipelineId || ''),
    () => getPipelineFilesQueryFn(pipelineId!),
    !!appId && !!pipelineId
  );
};

export const useGetAppById = (appId: string, enabled: boolean = true): UseQueryResult<App | undefined, Error> => {
  return useQueryInit<App | undefined>(getAppByIdKey(appId), () => getAppByIdFn(appId), enabled);
};
