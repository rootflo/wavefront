import floConsoleService from '@app/api';
import { IUser } from '@app/types/user';

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

/**
 * User mutation functions
 */
export const createUserMutationFn = async (data: {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}): Promise<IUser> => {
  const response = await floConsoleService.userService.createUser(data);
  if (!response.data.data) {
    throw new Error('Failed to create user');
  }
  return response.data.data.user;
};

export const updateUserMutationFn = async ({
  userId,
  data,
}: {
  userId: string;
  data: {
    email?: string;
    password?: string;
    first_name?: string;
    last_name?: string;
  };
}): Promise<IUser> => {
  const response = await floConsoleService.userService.updateUser(userId, data);
  if (!response.data.data) {
    throw new Error('Failed to update user');
  }
  return response.data.data.user;
};

export const deleteUserMutationFn = async (userId: string): Promise<void> => {
  await floConsoleService.userService.deleteUser(userId);
};
