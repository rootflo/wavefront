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
}
