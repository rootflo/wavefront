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
  public_url: string;
  private_url: string;
}) => {
  const { appId, appName, public_url, private_url } = data;
  const response = await floConsoleService.appService.updateApp(appId, {
    app_name: appName,
    public_url: public_url,
    private_url: private_url,
  });
  return response.data;
};
