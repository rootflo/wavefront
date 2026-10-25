import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';
import {
  UpdateGuardrailPolicyRequest,
  GuardrailPolicyData,
  GuardrailPolicyListData,
  GuardrailAdapterListData,
  PiiEntityListData,
  PiiPreviewData,
  PiiPreviewRequest,
  PolicyPreviewData,
  PolicyPreviewResponse,
  PolicyPreviewRequest,
  GuardrailPolicyResponse,
  GuardrailPolicyListResponse,
  GuardrailAdapterListResponse,
  PiiEntityListResponse,
  PiiPreviewResponse,
} from '@app/types/guardrails';

export class GuardrailsService {
  constructor(private http: AxiosInstance) {}

  async listPolicies(): Promise<GuardrailPolicyListResponse> {
    const response: IApiResponse<GuardrailPolicyListData> = await this.http.get(
      `/v1/:appId/floware/v1/guardrails/policies`
    );
    return response;
  }

  async getPolicy(namespace: string): Promise<GuardrailPolicyResponse> {
    const response: IApiResponse<GuardrailPolicyData> = await this.http.get(
      `/v1/:appId/floware/v1/guardrails/policies/${namespace}`
    );
    return response;
  }

  async updatePolicy(namespace: string, data: UpdateGuardrailPolicyRequest): Promise<GuardrailPolicyResponse> {
    const response: IApiResponse<GuardrailPolicyData> = await this.http.put(
      `/v1/:appId/floware/v1/guardrails/policies/${namespace}`,
      data
    );
    return response;
  }

  async deletePolicy(namespace: string): Promise<GuardrailPolicyResponse> {
    const response: IApiResponse<GuardrailPolicyData> = await this.http.delete(
      `/v1/:appId/floware/v1/guardrails/policies/${namespace}`
    );
    return response;
  }

  async listSupportedAdapters(): Promise<GuardrailAdapterListResponse> {
    const response: IApiResponse<GuardrailAdapterListData> = await this.http.get(
      `/v1/:appId/floware/v1/guardrails/adapters`
    );
    return response;
  }

  async listPiiEntities(): Promise<PiiEntityListResponse> {
    const response: IApiResponse<PiiEntityListData> = await this.http.get(
      `/v1/:appId/floware/v1/guardrails/pii/entities`
    );
    return response;
  }

  /** Run draft options against sample text. Persists nothing. */
  async previewPii(data: PiiPreviewRequest): Promise<PiiPreviewResponse> {
    const response: IApiResponse<PiiPreviewData> = await this.http.post(
      `/v1/:appId/floware/v1/guardrails/pii/preview`,
      data
    );
    return response;
  }
  /**
   * Run a whole draft policy against sample text, at both stages.
   *
   * Goes through the real engine, so composition, enforcement mode and
   * fail-closed misconfiguration all show up here exactly as they would in
   * production. Unlike updatePolicy this accepts a draft naming an unavailable
   * provider, because seeing that block is the point.
   */
  async previewPolicy(data: PolicyPreviewRequest): Promise<PolicyPreviewResponse> {
    const response: IApiResponse<PolicyPreviewData> = await this.http.post(
      `/v1/:appId/floware/v1/guardrails/policies/preview`,
      data
    );
    return response;
  }
}
