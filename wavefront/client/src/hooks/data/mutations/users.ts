import floConsoleService from '@app/api';
import { getConsoleUsersKey, getUserKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
    invalidate: ({ userId }) => [getUserKey(userId)],
  });
