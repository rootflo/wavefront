/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Type definitions for Tools
 *
 * This file contains two separate tool systems:
 * 1. Tools for Agents (workflow agents) - lines 8-64
 * 2. Tools for Voice Agents (voice agent function calling) - lines 67+
 */

import { IApiResponse } from '@app/lib/axios';

// ============================================================================
// TOOLS FOR AGENTS (Workflow Agents)
// ============================================================================

export interface Tool {
  name: string;
  description: string;
  parameters: Record<
    string,
    {
      type: string;
      description: string;
    }
  >;
  category: string;
}

export interface ToolDetails {
  name: string;
  parameters: {
    [key: string]: {
      type: string;
      description: string;
    };
  };
  description: string;
  required: string[];
  prefill_parameter_names: string[];
  category: string;
  prefilled_value: {
    [key: string]: string;
  };
  resource_name: string;
}

export interface ToolsDetailsData {
  name: string;
  prefilled_values: Array<{
    [key: string]: string;
  }>;
  display_name: string;
  description: string;
}

export interface ToolNamesData {
  message: string;
  data: {
    tool_details: ToolDetails;
    count: number;
  };
}

export interface ToolDetailsData {
  message: string;
  data: {
    tool: Tool;
  };
}

export type ToolNamesResponse = IApiResponse<ToolNamesData>;
export type ToolDetailsResponse = IApiResponse<ToolDetailsData>;

// ============================================================================
// TOOLS FOR VOICE AGENTS (Function Calling)
// ============================================================================

export type ToolType = 'api' | 'python';

export type AuthType = 'none' | 'bearer' | 'api_key';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

/**
 * API Tool Configuration
 */
export interface ApiToolConfig {
  method: HttpMethod;
  url: string;
  headers?: Record<string, string>;
  timeout?: number;
  auth_type?: AuthType;
  auth_credentials?: Record<string, string>;
}

/**
 * Python Tool Configuration (Phase 2)
 */
export interface PythonToolConfig {
  code_storage_key: string;
  cloud_run_url: string;
  timeout?: number;
  resource_limits?: {
    cpu?: string;
    memory?: string;
  };
}

/**
 * Voice Agent Tool (database model)
 */
export interface VoiceAgentTool {
  id: string;
  name: string;
  display_name: string;
  description: string;
  tool_type: ToolType;
  config: ApiToolConfig | PythonToolConfig;
  parameter_schema?: Record<string, any>;
  response_template?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
}

/**
 * Voice Agent Tool Association
 */
export interface VoiceAgentToolAssociation {
  id: string;
  voice_agent_id: string;
  tool_id: string;
  is_enabled: boolean;
  config_overrides?: Record<string, any>;
  priority: number;
  created_at: string;
  updated_at: string;
}

/**
 * Combined tool with association details (returned by GET /voice-agents/{id}/tools)
 */
export interface VoiceAgentToolWithAssociation extends VoiceAgentTool {
  association: {
    id: string;
    is_enabled: boolean;
    config_overrides?: Record<string, any>;
    priority: number;
  };
}

/**
 * Create Tool Request
 */
export interface CreateToolRequest {
  name: string;
  display_name: string;
  description: string;
  tool_type: ToolType;
  config: ApiToolConfig | PythonToolConfig;
  parameter_schema?: Record<string, any>;
  response_template?: string;
}

/**
 * Update Tool Request
 */
export interface UpdateToolRequest {
  display_name?: string;
  description?: string;
  config?: ApiToolConfig | PythonToolConfig;
  parameter_schema?: Record<string, any>;
  response_template?: string;
}

/**
 * Attach Tool to Agent Request
 */
export interface AttachToolToAgentRequest {
  tool_id: string;
  is_enabled?: boolean;
  config_overrides?: Record<string, any>;
  priority?: number;
}

/**
 * Update Agent Tool Association Request
 */
export interface UpdateAgentToolRequest {
  is_enabled?: boolean;
  config_overrides?: Record<string, any>;
  priority?: number;
}

/**
 * List Tools Query Parameters
 */
export interface ListToolsParams {
  tool_type?: ToolType;
  limit?: number;
  offset?: number;
}

/**
 * Tool execution result (from Pipecat)
 */
export interface ToolExecutionResult {
  success: boolean;
  status_code?: number;
  data?: any;
  error?: string;
}

/**
 * Response data for create/update/delete operations
 */
export interface ToolData {
  message: string;
  tool?: VoiceAgentTool;
  tool_id?: string;
}

/**
 * Response data for list operations
 */
export interface ToolListData {
  tools: VoiceAgentTool[];
  count?: number;
}

/**
 * Response data for agent tools operations
 */
export interface AgentToolsData {
  tools: VoiceAgentToolWithAssociation[];
  count?: number;
}

/**
 * Response types using IApiResponse wrapper
 */
export type ToolResponse = IApiResponse<ToolData>;
export type ToolDetailResponse = IApiResponse<VoiceAgentTool>;
export type ToolListResponse = IApiResponse<ToolListData>;
export type AgentToolsResponse = IApiResponse<AgentToolsData>;
