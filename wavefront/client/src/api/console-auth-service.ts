import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';

interface UserLogin {
  email: string;
  password: string;
}

export class ConsoleAuthService {
  constructor(private http: AxiosInstance) {}

  async authenticate(user: UserLogin): Promise<IApiResponse<{ user: { access_token: string } }>> {
    return this.http.post('/v1/authenticate', {
      email: user.email,
      password: user.password,
    });
  }

  async logout() {
    return this.http.post('/v1/logout');
  }
}
