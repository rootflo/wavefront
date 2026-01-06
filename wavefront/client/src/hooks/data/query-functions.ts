import floConsoleService from '@app/api';
import { DocumentData, InferenceData, KbData } from '@app/api/knowledge-base-service';
import { ModelData } from '@app/api/model-inference-service';
import { NamespaceItem } from '@app/api/namespace-service';
import { AgentApi, AgentListItem } from '@app/types/agent';
import { ApiServiceItem } from '@app/types/api-service';
import { Authenticator } from '@app/types/authenticator';
import { Datasource, ReadYamlData, Yaml } from '@app/types/datasource';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { MessageProcessor, MessageProcessorListItem } from '@app/types/message-processor';
import { Pipeline, PipelineFile, PipelineStatus } from '@app/types/pipeline';
import { SttConfig } from '@app/types/stt-config';
import { TelephonyConfig } from '@app/types/telephony-config';
import { ToolDetails } from '@app/types/tool';
import { TtsConfig } from '@app/types/tts-config';
import { IUser } from '@app/types/user';
import { VoiceAgent } from '@app/types/voice-agent';
import { WorkflowListItem, WorkflowPipelineListItem, WorkflowRunListData } from '@app/types/workflow';

const getAllAppsQueryFn = async () => {
  const {
    data: { data = { apps: [] } },
  } = await floConsoleService.appService.getAllApps();
  return data.apps;
};

const getCurrentUserQueryFn = async () => {
  const {
    data: { data = { user: null } },
  } = await floConsoleService.userService.whoAmI();
  return data.user;
};

const getAllDatasourcesQueryFn = async () => {
  const {
    data: { data = { datasources: [] } },
  } = await floConsoleService.datasourcesService.getAllDatasources();
  return data.datasources;
};

const getDatasourceQueryFn = async (datasourceId: string): Promise<Datasource | null> => {
  const response = await floConsoleService.datasourcesService.getDatasource(datasourceId);
  if (response.data?.data) {
    const responseData = response.data.data as {
      name?: string;
      type?: string;
      config?: string | Record<string, unknown>;
      description?: string;
      created_at?: string;
      updated_at?: string;
    };
    return {
      id: datasourceId,
      name: responseData.name || 'Unknown',
      type: responseData.type || 'unknown',
      config: typeof responseData.config === 'string' ? JSON.parse(responseData.config) : responseData.config || {},
      description: responseData.description || '',
      created_at: responseData.created_at,
      updated_at: responseData.updated_at,
    };
  }
  return null;
};

const getAllYamlsQueryFn = async (datasourceId: string): Promise<Yaml[]> => {
  const response = await floConsoleService.datasourcesService.getAllYamls(datasourceId);
  if (response.data?.data?.yamls) {
    return response.data.data.yamls;
  }
  return [];
};

const readYamlQueryFn = async (datasourceId: string, yamlId: string): Promise<ReadYamlData | null> => {
  const response = await floConsoleService.datasourcesService.readYaml(datasourceId, yamlId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getDatasourceResourcesQueryFn = async (datasourceId: string): Promise<string[]> => {
  const response = await floConsoleService.datasourcesService.getDatasourceResources(datasourceId);
  if (response.data?.data?.data?.resources) {
    return response.data.data.data.resources;
  }
  return [];
};

const getAgentsQueryFn = async (namespace?: string): Promise<AgentListItem[]> => {
  const response = await floConsoleService.agentService.listAgents(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.agents;
  }
  return [];
};

const getNamespacesQueryFn = async (): Promise<NamespaceItem[]> => {
  const response = await floConsoleService.namespaceService.listNamespaces();
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.namespaces;
  }
  return [];
};

const getApiServicesQueryFn = async (): Promise<ApiServiceItem[]> => {
  const response = await floConsoleService.apiServiceService.listApiServices();
  if (response.data?.meta?.status === 'success' && response.data.data?.services) {
    return response.data.data.services;
  }
  return [];
};

const getAuthenticatorsQueryFn = async (): Promise<Authenticator[]> => {
  const response = await floConsoleService.authenticatorService.getAllAuthenticators();
  if (response.data?.meta?.status === 'success' && response.data.data?.authenticators) {
    return response.data.data.authenticators;
  }
  return [];
};

const getAuthenticatorQueryFn = async (authId: string): Promise<Authenticator | null> => {
  const response = await floConsoleService.authenticatorService.getAuthenticator(authId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getLLMConfigsQueryFn = async (): Promise<LLMInferenceConfig[]> => {
  const response = await floConsoleService.llmInferenceService.listAllLLMConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.configs) {
    return response.data.data.configs;
  }
  return [];
};

const getModelsQueryFn = async (): Promise<ModelData[]> => {
  const response = await floConsoleService.modelInferenceService.listAllModels();
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data;
  }
  return [];
};

const getModelQueryFn = async (modelId: string): Promise<ModelData | null> => {
  const response = await floConsoleService.modelInferenceService.getModel(modelId);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data;
  }
  return null;
};

const getKnowledgeBasesQueryFn = async (): Promise<KbData[]> => {
  const response = await floConsoleService.knowledgeBaseService.listKnowledgeBases();
  if (response.data?.meta?.status === 'success' && response.data.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

const getKnowledgeBaseQueryFn = async (kbId: string): Promise<KbData | null> => {
  const response = await floConsoleService.knowledgeBaseService.getKnowledgeBase(kbId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getKnowledgeBaseDocumentsQueryFn = async (kbId: string): Promise<DocumentData[]> => {
  const response = await floConsoleService.knowledgeBaseService.listKnowledgeBaseDocuments(kbId);
  if (response.data?.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

const getKnowledgeBaseInferencesQueryFn = async (kbId: string): Promise<InferenceData[]> => {
  const response = await floConsoleService.knowledgeBaseService.listInferencesForKnowledgeBase(kbId);
  if (response.data?.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

const getWorkflowsQueryFn = async (namespace?: string): Promise<WorkflowListItem[]> => {
  const response = await floConsoleService.workflowService.listWorkflows(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.workflows;
  }
  return [];
};

const getWorkflowPipelinesQueryFn = async (): Promise<WorkflowPipelineListItem[]> => {
  const response = await floConsoleService.workflowService.listWorkflowPipelines();
  if (response.data?.meta?.status === 'success' && response.data.data?.workflow_pipelines) {
    return response.data.data.workflow_pipelines;
  }
  return [];
};

const getWorkflowRunsQueryFn = async (
  workflowPipelineId: string,
  offset: number = 0,
  limit: number = 10
): Promise<WorkflowRunListData> => {
  const response = await floConsoleService.workflowService.getWorkflowRuns(workflowPipelineId, offset, limit);
  if (response.data?.meta?.status === 'success' && response.data.data) {
    return response.data.data;
  }
  return {
    workflow_runs: [],
    total_count: 0,
    page_size: limit,
    page_number: Math.floor(offset / limit),
    total_pages: 0,
  };
};

const getVoiceAgentsQueryFn = async (): Promise<VoiceAgent[]> => {
  const response = await floConsoleService.voiceAgentService.listAllVoiceAgents();
  if (response.data?.meta?.status === 'success' && response.data.data?.voice_agents) {
    return response.data.data.voice_agents;
  }
  return [];
};

const getTtsConfigsQueryFn = async (): Promise<TtsConfig[]> => {
  const response = await floConsoleService.ttsConfigService.listAllTtsConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.tts_configs) {
    return response.data.data.tts_configs;
  }
  return [];
};

const getSttConfigsQueryFn = async (): Promise<SttConfig[]> => {
  const response = await floConsoleService.sttConfigService.listAllSttConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.stt_configs) {
    return response.data.data.stt_configs;
  }
  return [];
};

const getTelephonyConfigsQueryFn = async (): Promise<TelephonyConfig[]> => {
  const response = await floConsoleService.telephonyConfigService.listAllTelephonyConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.telephony_configs) {
    return response.data.data.telephony_configs;
  }
  return [];
};

const getVoiceAgentQueryFn = async (agentId: string): Promise<VoiceAgent | null> => {
  const response = await floConsoleService.voiceAgentService.getVoiceAgent(agentId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getTtsConfigQueryFn = async (configId: string): Promise<TtsConfig | null> => {
  const response = await floConsoleService.ttsConfigService.getTtsConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getSttConfigQueryFn = async (configId: string): Promise<SttConfig | null> => {
  const response = await floConsoleService.sttConfigService.getSttConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getTelephonyConfigQueryFn = async (configId: string): Promise<TelephonyConfig | null> => {
  const response = await floConsoleService.telephonyConfigService.getTelephonyConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getAgentQueryFn = async (agentId: string): Promise<AgentApi | null> => {
  const response = await floConsoleService.agentService.getAgent(agentId);
  if (response.data?.data?.data) {
    return {
      id: response.data.data.data.id,
      name: response.data.data.data.name,
      namespace: response.data.data.data.namespace,
      created_at: response.data.data.data.created_at,
      updated_at: response.data.data.data.updated_at,
      yaml_content: response.data.data.data.yaml_content || '',
    };
  }
  return null;
};

const getToolsQueryFn = async (): Promise<ToolDetails[]> => {
  const response = await floConsoleService.toolService.getToolNamesAndDetails();
  if (response.data?.data?.data?.tool_details && Array.isArray(response.data.data.data.tool_details)) {
    return response.data.data.data.tool_details;
  }
  return [];
};

const getMessageProcessorsQueryFn = async (): Promise<MessageProcessorListItem[]> => {
  const response = await floConsoleService.messageProcessorService.listMessageProcessors();
  if (response.data?.data?.processors && Array.isArray(response.data.data.processors)) {
    return response.data.data.processors;
  }
  return [];
};

const getMessageProcessorQueryFn = async (processorId: string): Promise<MessageProcessor | null> => {
  const response = await floConsoleService.messageProcessorService.getMessageProcessor(processorId);
  if (response.data?.data?.processor) {
    return response.data.data.processor;
  }
  return null;
};

const getApiServiceQueryFn = async (serviceId: string): Promise<ApiServiceItem | null> => {
  const response = await floConsoleService.apiServiceService.getApiService(serviceId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getLLMConfigQueryFn = async (configId: string): Promise<LLMInferenceConfig | null> => {
  const response = await floConsoleService.llmInferenceService.getLLMConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getPipelinesQueryFn = async (statusFilter?: PipelineStatus | 'all'): Promise<Pipeline[]> => {
  const pipelineService = floConsoleService.dataPipelineService;
  const response = await (statusFilter === 'all' || !statusFilter
    ? pipelineService.listPipelines()
    : pipelineService.listPipelines(statusFilter));
  if (response.data?.data?.pipelines) {
    return response.data.data.pipelines;
  }
  return [];
};

const getPipelineQueryFn = async (pipelineId: string): Promise<Pipeline | null> => {
  const pipelineService = floConsoleService.dataPipelineService;
  const response = await pipelineService.getPipeline(pipelineId);
  if (response.data?.data?.pipeline) {
    return response.data.data.pipeline;
  }
  return null;
};

const getPipelineFilesQueryFn = async (pipelineId: string): Promise<PipelineFile[]> => {
  const pipelineService = floConsoleService.dataPipelineService;
  const response = await pipelineService.listFiles(pipelineId);
  if (response.data?.data?.files) {
    return response.data.data.files;
  }
  return [];
};

const getAppByIdFn = async (appId: string) => {
  const {
    data: { data },
  } = await floConsoleService.appService.getAppById(appId);
  return data?.app;
};

const getUsersQueryFn = async (): Promise<IUser[]> => {
  const response = await floConsoleService.userService.listUsers();
  if (response.data?.data?.users && Array.isArray(response.data.data.users)) {
    return response.data.data.users;
  }
  return [];
};

export {
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
  getUsersQueryFn,
  readYamlQueryFn,
};
