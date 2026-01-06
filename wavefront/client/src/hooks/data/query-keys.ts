const getAgentsKey = (appId: string, namespace?: string) => {
  if (namespace) {
    return ['agents', appId, namespace];
  }
  return ['agents', appId];
};
const getNamespacesKey = (appId: string) => ['namespaces', appId];
const getAllAppsKey = () => ['apps'];
const getAllDatasourcesKey = (appId: string) => ['datasources', appId];
const getDatasourceKey = (appId: string, datasourceId: string) => ['datasource', appId, datasourceId];
const getAllYamlsKey = (appId: string, datasourceId: string) => ['yamls', appId, datasourceId];
const readYamlKey = (appId: string, datasourceId: string, yamlId: string) => ['yaml', appId, datasourceId, yamlId];
const getDatasourceResourcesKey = (appId: string, datasourceId: string) => [
  'datasource-resources',
  appId,
  datasourceId,
];
const getCurrentUserKey = () => ['whoami'];
const getApiServicesKey = (appId: string) => ['api-services', appId];
const getAuthenticatorsKey = (appId: string) => ['authenticators', appId];
const getAuthenticatorKey = (appId: string, authId: string) => ['authenticator', appId, authId];
const getLLMConfigsKey = (appId: string) => ['llm-configs', appId];
const getLLMConfigKey = (appId: string, configId: string) => ['llm-config', appId, configId];
const getModelsKey = (appId: string) => ['models', appId];
const getModelKey = (appId: string, modelId: string) => ['model', appId, modelId];
const getKnowledgeBasesKey = (appId: string) => ['knowledge-bases', appId];
const getKnowledgeBaseKey = (appId: string, kbId: string) => ['knowledge-base', appId, kbId];
const getKnowledgeBaseDocumentsKey = (appId: string, kbId: string) => ['knowledge-base-documents', appId, kbId];
const getKnowledgeBaseInferencesKey = (appId: string, kbId: string) => ['knowledge-base-inferences', appId, kbId];
const getWorkflowsKey = (appId: string, namespace?: string) => {
  if (namespace) {
    return ['workflows', appId, namespace];
  }
  return ['workflows', appId];
};
const getWorkflowPipelinesKey = (appId: string) => ['workflow-pipelines', appId];
const getWorkflowRunsKey = (appId: string, workflowPipelineId: string, offset?: number, limit?: number) => {
  const key: (string | number)[] = ['workflow-runs', appId, workflowPipelineId];
  if (offset !== undefined) key.push('offset', offset);
  if (limit !== undefined) key.push('limit', limit);
  return key;
};
const getVoiceAgentsKey = (appId: string) => ['voice-agents', appId];
const getTtsConfigsKey = (appId: string) => ['tts-configs', appId];
const getSttConfigsKey = (appId: string) => ['stt-configs', appId];
const getTelephonyConfigsKey = (appId: string) => ['telephony-configs', appId];
const getVoiceAgentKey = (appId: string, agentId: string) => ['voice-agent', appId, agentId];
const getTtsConfigKey = (appId: string, configId: string) => ['tts-config', appId, configId];
const getSttConfigKey = (appId: string, configId: string) => ['stt-config', appId, configId];
const getTelephonyConfigKey = (appId: string, configId: string) => ['telephony-config', appId, configId];
const getAgentKey = (appId: string, agentId: string) => ['agent', appId, agentId];
const getToolsKey = (appId: string) => ['tools', appId];
const getApiServiceKey = (appId: string, serviceId: string) => ['api-service', appId, serviceId];
const getMessageProcessorsKey = (appId: string) => ['message-processors', appId];
const getMessageProcessorKey = (appId: string, processorId: string) => ['message-processor', appId, processorId];
const getPipelinesKey = (appId: string, statusFilter?: string) => {
  if (statusFilter) {
    return ['pipelines', appId, statusFilter];
  }
  return ['pipelines', appId];
};
const getPipelineKey = (appId: string, pipelineId: string) => ['pipeline', appId, pipelineId];
const getPipelineFilesKey = (appId: string, pipelineId: string) => ['pipeline-files', appId, pipelineId];
const getAppByIdKey = (appId: string) => ['app-by-id', appId];
const getUsersKey = () => ['users'];
const getUserKey = (userId: string) => ['user', userId];

export {
  getAgentKey,
  getAgentsKey,
  getAllAppsKey,
  getAllDatasourcesKey,
  getApiServiceKey,
  getApiServicesKey,
  getAuthenticatorKey,
  getAuthenticatorsKey,
  getCurrentUserKey,
  getDatasourceKey,
  getDatasourceResourcesKey,
  getAllYamlsKey,
  readYamlKey,
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
  getAppByIdKey,
  getUserKey,
  getUsersKey,
};
