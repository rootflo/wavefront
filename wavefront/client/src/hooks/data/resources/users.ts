import floConsoleService from '@app/api';
import { IUser } from '@app/types/user';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getCurrentUserKey, getAppUsersKey, getConsoleUsersKey, getUserKey, getUserAppsKey } from '../query-keys';

// Reads

const getCurrentUserQueryFn = async () => {
  const {
    data: { data = { user: null } },
  } = await floConsoleService.userService.whoAmI();
  return data.user;
};

const getAppUsersQueryFn = async (): Promise<IUser[]> => {
  const response = await floConsoleService.appUserService.listAppUsers();
  if (response.data?.data?.users && Array.isArray(response.data.data.users)) {
    return response.data.data.users;
  }
  return [];
};

const getConsoleUsersQueryFn = async (): Promise<IUser[]> => {
  const response = await floConsoleService.userService.listUsers();
  if (response.data?.data?.users && Array.isArray(response.data.data.users)) {
    return response.data.data.users;
  }
  return [];
};

export const useGetCurrentUser = (enabled: boolean): UseQueryResult<IUser | null, Error> => {
  return useQueryInit(getCurrentUserKey(), getCurrentUserQueryFn, enabled);
};

export const useGetAppUsers = (appId: string | undefined): UseQueryResult<IUser[], Error> => {
  return useQueryInit(getAppUsersKey(appId || ''), () => getAppUsersQueryFn(), !!appId);
};

export const useGetConsoleUsers = (): UseQueryResult<IUser[], Error> => {
  return useQueryInit(getConsoleUsersKey(), getConsoleUsersQueryFn, true);
};

/** The IDs of the apps a console user can access. */
export const useGetUserApps = (userId: string | undefined, enabled = true): UseQueryResult<string[], Error> =>
  useQueryInit(
    getUserAppsKey(userId || ''),
    async () => (await floConsoleService.appUserService.listUserApps(userId!)).data.data?.app_ids ?? [],
    enabled && !!userId
  );

// Writes

type CreateUserRequest = Parameters<typeof floConsoleService.userService.createUser>[0];
type UpdateUserRequest = Parameters<typeof floConsoleService.userService.updateUser>[1];

export const useCreateUser = () =>
  useResourceMutation({
    mutationFn: (data: CreateUserRequest) => floConsoleService.userService.createUser(data),
    successMessage: 'User created successfully',
    errorMessage: 'Failed to create user',
    invalidate: () => [getConsoleUsersKey()],
  });

export const useUpdateUser = () =>
  useResourceMutation({
    mutationFn: ({ userId, data }: { userId: string; data: UpdateUserRequest }) =>
      floConsoleService.userService.updateUser(userId, data),
    successMessage: 'User updated successfully',
    errorMessage: 'Failed to update user',
    invalidate: ({ userId }) => [getConsoleUsersKey(), getUserKey(userId)],
  });

export const useDeleteUser = () =>
  useResourceMutation({
    mutationFn: (userId: string) => floConsoleService.userService.deleteUser(userId),
    successMessage: 'User deleted successfully',
    errorMessage: 'Failed to delete user',
    invalidate: () => [getConsoleUsersKey()],
  });

/** Grants and revokes so the user ends up with access to exactly `appIds`. */
export const useUpdateUserAppAccess = () =>
  useResourceMutation({
    mutationFn: async ({ userId, appIds }: { userId: string; appIds: string[] }) => {
      const response = await floConsoleService.appUserService.listUserApps(userId);
      const current = new Set(response.data.data?.app_ids ?? []);
      const wanted = new Set(appIds);
      for (const appId of wanted) {
        if (!current.has(appId)) await floConsoleService.appUserService.grantAppAccess(appId, userId);
      }
      for (const appId of current) {
        if (!wanted.has(appId)) await floConsoleService.appUserService.revokeAppAccess(appId, userId);
      }
    },
    successMessage: 'App access updated successfully',
    errorMessage: 'Failed to update app access',
    invalidate: ({ userId }) => [getUserAppsKey(userId)],
  });
