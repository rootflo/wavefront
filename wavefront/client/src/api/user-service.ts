import { IApiResponse } from '@app/lib/axios';
import { IUser } from '@app/types/user';
import { AxiosInstance } from 'axios';

export class UserService {
  constructor(private http: AxiosInstance) {}

  async whoAmI(): Promise<IApiResponse<{ user: IUser }>> {
    return this.http.get('/v1/whoami');
  }

  async resetPassword(token: string, password: string) {
    return this.http.post('/v1/user/reset-password', {
      secret_token: token,
      new_password: password,
    });
  }

  async resetPasswordEmailSend(email: string) {
    return this.http.post('/v1/user/send-reset-password-email', null, {
      params: {
        email: email,
      },
    });
  }

  async listUsers(): Promise<IApiResponse<{ users: IUser[] }>> {
    return this.http.get('/v1/users');
  }

  async createUser(data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }): Promise<IApiResponse<{ user: IUser }>> {
    return this.http.post('/v1/users', data);
  }

  async updateUser(
    userId: string,
    data: {
      email?: string;
      password?: string;
      first_name?: string;
      last_name?: string;
    }
  ): Promise<IApiResponse<{ user: IUser }>> {
    return this.http.patch(`/v1/users/${userId}`, data);
  }

  async deleteUser(userId: string): Promise<IApiResponse<{ message: string }>> {
    return this.http.delete(`/v1/users/${userId}`);
  }
}
