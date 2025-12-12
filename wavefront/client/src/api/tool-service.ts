import { IApiResponse } from "@app/lib/axios";
import {
  ToolDetailsData,
  ToolDetailsResponse,
  ToolNamesData,
  ToolNamesResponse,
} from "@app/types/tool";
import { AxiosInstance } from "axios";

export class ToolService {
  constructor(private http: AxiosInstance) {}

  async getToolNames(): Promise<ToolNamesResponse> {
    const response: IApiResponse<ToolNamesData> = await this.http.get(
      `/v1/:appId/floware/v1/tools/names`
    );
    return response;
  }

  async getToolNamesAndDetails(): Promise<ToolNamesResponse> {
    const response: IApiResponse<ToolNamesData> = await this.http.get(
      `/v1/:appId/floware/v1/tools/tool-details`
    );
    return response;
  }

  async getToolDetails(toolName: string): Promise<ToolDetailsResponse> {
    const response: IApiResponse<ToolDetailsData> = await this.http.get(
      `/v1/:appId/floware/v1/tools/${toolName}`
    );
    return response;
  }
}
