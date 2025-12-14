import { IApiResponse } from '@app/lib/axios';

// App Management Types
export interface App {
  id: string;
  app_name: string;
  created_at: string;
  config: Record<string, string>;
  public_url: string;
  private_url: string;
  status: string;
  updated_at: string | null;
}

export interface CreateAppRequest {
  app_name: string;
  deployment_type: string;
  public_url: string;
  private_url: string;
}

export interface UpdateAppRequest {
  app_name?: string;
  public_url?: string;
  private_url?: string;
}

export interface AppData {
  app: App;
}

export interface AppsData {
  apps: App[];
}

export interface DeleteAppData {
  message: string;
}

export interface AppStatusData {
  status: string;
}

export type AppResponse = IApiResponse<AppData>;
export type AppsResponse = IApiResponse<AppsData>;
export type DeleteAppResponse = IApiResponse<DeleteAppData>;
export type AppStatusResponse = IApiResponse<AppStatusData>;
