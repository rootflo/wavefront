import { IApiResponse } from '@app/lib/axios';
import { IUser } from '@app/types/user';
import { AxiosInstance } from 'axios';

export class AppUserService {
  constructor(private http: AxiosInstance) {}

  /**
   * Grant user access to an app (owners only)
   */
  async grantAppAccess(appId: string, userId: string): Promise<IApiResponse<{ message: string }>> {
    return this.http.post(`/v1/apps/${appId}/users/${userId}`);
  }

  /**
   * Revoke user access from an app (owners only)
   */
  async revokeAppAccess(appId: string, userId: string): Promise<IApiResponse<{ message: string }>> {
    return this.http.delete(`/v1/apps/${appId}/users/${userId}`);
  }

  /**
   * List users with access to an app (owners only)
   */
  async listAppUsers(appId: string): Promise<IApiResponse<{ users: IUser[] }>> {
    return this.http.get(`/v1/apps/${appId}/users`);
  }

  /**
   * List apps accessible to a user (owners only)
   */
  async listUserApps(userId: string): Promise<IApiResponse<{ app_ids: string[] }>> {
    return this.http.get(`/v1/users/${userId}/apps`);
  }
}
