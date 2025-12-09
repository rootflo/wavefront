import floConsoleService from "@app/api";

/**
 * Agent mutation functions
 */
export const deleteAgentMutationFn = async (agentId: string): Promise<void> => {
  await floConsoleService.agentService.deleteAgent(agentId);
};

export const updateAgentMutationFn = async ({
  agentId,
  yamlContent,
}: {
  agentId: string;
  yamlContent: string;
}): Promise<void> => {
  await floConsoleService.agentService.updateAgent(agentId, yamlContent);
};

export const updateAppFn = async (data: {
  appId: string;
  appName: string;
  appUrl: string;
  appKey: string;
  appSecret: string;
}) => {
  const { appId, appName, appUrl, appKey, appSecret } = data;
  const response = await floConsoleService.appService.updateApp(appId, {
    app_name: appName,
    app_url: appUrl,
    app_key: appKey,
    app_secret: appSecret,
  });
  return response.data;
};
