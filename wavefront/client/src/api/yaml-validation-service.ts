import http from '@app/lib/axios';
import { AxiosInstance } from 'axios';
import { YamlValidationResponse } from '@app/types/yaml-validation';

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
