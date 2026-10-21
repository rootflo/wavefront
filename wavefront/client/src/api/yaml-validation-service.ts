import http, { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';

/** One problem found in a YAML document, located by its path (empty for the whole document). */
export interface YamlValidationError {
  path: string;
  message: string;
}

export interface YamlValidationResult {
  valid: boolean;
  errors: YamlValidationError[];
}

export interface YamlValidationData {
  message: string;
  data: YamlValidationResult;
}

export type YamlValidationResponse = IApiResponse<YamlValidationData>;

/**
 * Validates agent and workflow YAML on the server without saving it. A document with
 * problems still answers 200 with `valid: false`, so read `data.data.errors` rather
 * than expecting a rejected promise.
 */
export class YamlValidationService {
  constructor(private http: AxiosInstance) {}

  async validateAgentYaml(yamlContent: string): Promise<YamlValidationResponse> {
    const response: YamlValidationResponse = await this.http.post(
      '/v1/:appId/floware/v1/agent-management/agents:validate',
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
      }
    );
    return response;
  }

  async validateWorkflowYaml(yamlContent: string): Promise<YamlValidationResponse> {
    const response: YamlValidationResponse = await this.http.post(
      '/v1/:appId/floware/v1/workflow-management/workflows:validate',
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
      }
    );
    return response;
  }
}

export const yamlValidationService = new YamlValidationService(http);
