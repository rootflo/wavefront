import { appEnv } from '@app/config/env';
import { TOKEN_KEY } from '@app/lib/constants';
import { getRouteAppId } from '@app/lib/current-app';
import { clearSession } from '@app/lib/session';
import { extractErrorMessage } from '@app/lib/errors';
import { useAuthStore, useNotifyStore } from '@app/store';
import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

export interface Meta {
  status: 'success' | 'failure';
  code: number;
  error?: string;
}
export interface ApiResponse<T = unknown> {
  meta: Meta;
  data?: T;
}
export type IAxiosError = AxiosError;
export type IApiResponse<T = unknown> = AxiosResponse<ApiResponse<T>>;

const axiosInstance = axios.create({
  baseURL: appEnv.baseURL,
});

axiosInstance.interceptors.request.use(
  function (config: InternalAxiosRequestConfig) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // App-scoped endpoints are written with an :appId placeholder, filled from the page's app
    if (config.url?.includes(':appId')) {
      const appId = getRouteAppId();
      if (!appId) {
        // Fail loudly rather than send the request to the wrong app or to none
        throw new Error(`${config.url} needs an app, but this page is not inside one`);
      }
      config.url = config.url.replace(':appId', encodeURIComponent(appId));
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
    // The one error toast for every request; a mutation hook may replace it with a more specific fallback.
    // A cancelled request was abandoned on purpose, so it isn't reported.
    if (!axios.isCancel(err)) {
      useNotifyStore.setState({
        visible: true,
        type: 'error',
        // A network failure or timeout has no response, so this must not assume one
        message: extractErrorMessage(err) || 'Something went wrong',
      });
    }
    const errCode = err.response?.status;
    if (errCode === 401) {
      clearSession();
      useAuthStore.setState({
        authenticated: false,
      });
      window.location.href = '/login';
    }

    return Promise.reject(err);
  }
);

export default axiosInstance;
