import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';

export type WorkflowStage = 'BEFORE_MODEL' | 'AFTER_MODEL';
export type FailureMode = 'FAIL_OPEN' | 'FAIL_CLOSED';
export type EnforcementMode = 'MONITOR' | 'ENFORCE';

/**
 * Whether a streamed response may be shown before it has all been checked.
 *
 * BUFFERED withholds it until the whole response has been vetted.
 * INCREMENTAL releases it as it arrives, holding back enough of the tail that
 * a finding cannot straddle the boundary. INCREMENTAL only takes effect where
 * every configured provider supports it, so what was asked for and what
 * happens can differ -- see `effective_stream_mode` on the save response.
 */
export type StreamPreference = 'BUFFERED' | 'INCREMENTAL';

export interface GuardrailAdapterConfig {
  name: string;
  stages: WorkflowStage[];
  /**
   * Applies only to provider outages, timeouts and throttling. Oversized or
   * wrongly-typed input always fails closed regardless of this setting,
   * because the caller controls it and could otherwise opt out on demand.
   */
  on_error: FailureMode;
  timeout_seconds: number;
  options: Record<string, unknown>;
}

export interface GuardrailPolicy {
  namespace: string;
  /** Master switch. When false, no safety provider is called at all. */
  is_enabled: boolean;
  /** MONITOR records verdicts without acting; ENFORCE blocks and redacts. */
  mode: EnforcementMode;
  adapters: GuardrailAdapterConfig[];
  stream: StreamPreference;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpdateGuardrailPolicyRequest {
  is_enabled: boolean;
  mode: EnforcementMode;
  adapters: GuardrailAdapterConfig[];
  /**
   * Must be sent on every save. The server replaces `policy_config` wholesale,
   * so omitting this silently reverts the namespace to BUFFERED.
   */
  stream: StreamPreference;
}

export interface GuardrailPolicyData {
  policy: GuardrailPolicy;
}

export interface GuardrailPolicyListData {
  policies: GuardrailPolicy[];
}

export interface GuardrailAdapterListData {
  /** Providers the server actually registered and can run. */
  adapters: string[];
  /** Known providers whose dependencies or credentials are missing. */
  unavailable?: string[];
}

/**
 * How much to trust a detection.
 *
 * `validated` runs a checksum or a dedicated library, so it only fires on real
 * identifiers. `pattern` is a regex alone — some are very loose. `nlp` is the
 * language model, which is context-dependent and fires on ordinary prose.
 */
export type PiiPrecision = 'validated' | 'pattern' | 'nlp';

export interface PiiEntity {
  id: string;
  label: string;
  description: string;
  country_code: string | null;
  example: string | null;
  precision: PiiPrecision;
  /** Weakest pattern confidence; low values match loosely. Null for NLP. */
  min_pattern_score: number | null;
  /** Part of the provider's default set when no selection is stored. */
  default_selected: boolean;
}

export interface PiiEntityGroup {
  group: string;
  country_code: string | null;
  entities: PiiEntity[];
}

export interface PiiEntityListData {
  groups: PiiEntityGroup[];
  /** False when the PII provider is not registered on this deployment. */
  available: boolean;
}

export interface PiiPreviewFinding {
  entity_type: string;
  start: number;
  end: number;
  score: number;
}

export interface PiiPreviewResult {
  redacted_text: string;
  findings: PiiPreviewFinding[];
}

export interface PiiPreviewData {
  result: PiiPreviewResult;
}

export interface PiiPreviewRequest {
  text: string;
  options: Record<string, unknown>;
}

/** One adapter's verdict inside a policy preview. */
export interface PolicyPreviewResult {
  adapter: string | null;
  status: string;
  action: 'ALLOW' | 'BLOCK' | 'TRANSFORM';
  finding_code: string | null;
  message: string | null;
  severity: number | null;
  failure_class: 'NONE' | 'INFRASTRUCTURE' | 'INPUT_REJECTED' | 'MISCONFIGURED';
  metadata: Record<string, unknown>;
}

export interface PolicyPreviewStage {
  stage: WorkflowStage;
  /** What the policy does. In MONITOR this is always ALLOW. */
  action: 'ALLOW' | 'BLOCK' | 'TRANSFORM';
  /** What it would have done. Populated in MONITOR too. */
  observed_action: 'ALLOW' | 'BLOCK' | 'TRANSFORM';
  enforced: boolean;
  transformed_text: string | null;
  results: PolicyPreviewResult[];
}

export interface PolicyPreviewData {
  stages: PolicyPreviewStage[];
}

export type PolicyPreviewResponse = IApiResponse<PolicyPreviewData>;

/** A draft policy plus the text to run it against. Same shape as a save. */
export interface PolicyPreviewRequest extends UpdateGuardrailPolicyRequest {
  text: string;
}

export type GuardrailPolicyResponse = IApiResponse<GuardrailPolicyData>;
export type GuardrailPolicyListResponse = IApiResponse<GuardrailPolicyListData>;
export type GuardrailAdapterListResponse = IApiResponse<GuardrailAdapterListData>;
export type PiiEntityListResponse = IApiResponse<PiiEntityListData>;
export type PiiPreviewResponse = IApiResponse<PiiPreviewData>;

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
