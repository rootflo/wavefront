import { appEnv } from '@app/config/env';
import { TOKEN_KEY } from '@app/lib/constants';
import { useAuthStore, useNotifyStore } from '@app/store';
import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

export interface Meta {
  status: 'success' | 'failure';
  code: number;
  error?: string;
}
export interface ApiResponse<T = any> {
  meta: Meta;
  data?: T;
}
export type IAxiosError = AxiosError;
export type IApiResponse<T = any> = AxiosResponse<ApiResponse<T>>;

const axiosInstance = axios.create({
  baseURL: appEnv.baseURL,
});

axiosInstance.interceptors.request.use(
  function (config: InternalAxiosRequestConfig) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Replace :appId with the actual appId from the URL
    if (config.url?.includes(':appId')) {
      const pageUrl = new URL(window.location.href);
      const appId = pageUrl.pathname.split('/')[2];
      config.url = config.url?.replace(':appId', appId || '');
    }

    return config;
  },
  function (error: AxiosError) {
    return Promise.reject(error);
  }
);

axiosInstance.interceptors.response.use(
  function <T>(response: IApiResponse<T>) {
    return response;
  },
  function (err: IAxiosError) {
    const errorData = err.response as IApiResponse;
    useNotifyStore.setState({
      visible: true,
      type: 'error',
      message: errorData.data?.meta?.error || 'Something went wrong',
    });
    const errCode = err.response?.status;
    if (errCode === 401) {
      localStorage.clear();
      useAuthStore.setState({
        authenticated: false,
      });
      window.location.href = '/login';
    }

    return Promise.reject(err);
  }
);

export default axiosInstance;
