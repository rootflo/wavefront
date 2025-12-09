import { IApiResponse } from "@app/lib/axios";

// App Management Types
export interface App {
  id: string;
  app_name: string;
  app_url: string;
  app_key: string;
  created_at: string;
  updated_at: string | null;
  status: string;
  config: Record<string, string>;
}

export interface CreateAppRequest {
  app_name: string;
  app_url: string;
  app_secret: string;
  app_key: string;
  deployment_type: string;
}

export interface UpdateAppRequest {
  app_name?: string;
  app_url?: string;
  app_secret?: string;
  app_key?: string;
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
