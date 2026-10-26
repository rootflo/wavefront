import { ApiServiceItem } from '@app/types/api-service';
import yaml from 'js-yaml';
import { z } from 'zod';

// The API service form: its schema, and conversion between the form, the service YAML and the API's service

const keyValuePairSchema = z.object({
  key: z.string(),
  value: z.string(),
});

const payloadFieldSchema = z.object({
  name: z.string(),
  type: z.enum(['string', 'integer', 'number', 'boolean', 'array', 'object']),
  required: z.boolean(),
  description: z.string(),
});

const apiEndpointSchema = z.object({
  id: z.string(),
  version: z.string(),
  path: z.string(),
  backend_path: z.string(),
  method: z.enum(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']),
  description: z.string().optional(),
  additional_headers: z.array(keyValuePairSchema),
  backend_query_params: z.array(keyValuePairSchema),
  output_mapper_enabled: z.boolean(),
  output_mapper: z.array(keyValuePairSchema),
  payload_schema: z
    .object({
      fields: z.array(payloadFieldSchema),
    })
    .optional(),
});

export const apiServiceFormSchema = z.object({
  id: z.string().min(1, 'Service ID is required'),
  base_url: z.string().min(1, 'Base URL is required'),
  auth: z.object({
    id: z.string(),
    version: z.string(),
    type: z.enum(['basic', 'bearer', 'api_key', 'none']),
    base_url: z.string().optional(),
    path: z.string().optional(),
    username: z.string().optional(),
    password: z.string().optional(),
    token: z.string().optional(),
    api_key: z.string().optional(),
    api_key_header: z.string().optional(),
    additional_headers: z.array(keyValuePairSchema),
  }),
  apis: z.array(apiEndpointSchema),
});

export type ApiServiceForm = z.infer<typeof apiServiceFormSchema>;

type ParsedYamlAuth = {
  id?: string;
  version?: string;
  type?: 'basic' | 'bearer' | 'api_key' | 'none';
  base_url?: string;
  path?: string;
  username?: string;
  password?: string;
  token?: string;
  api_key?: string;
  api_key_header?: string;
  additional_headers?: Record<string, string>;
};

type ParsedYamlService = {
  id?: string;
  base_url?: string;
  auth?: ParsedYamlAuth;
  apis?: Array<{
    id?: string;
    version?: string;
    path?: string;
    backend_path?: string;
    method?: string;
    description?: string;
    additional_headers?: Record<string, string>;
    backend_query_params?: Record<string, unknown>;
    output_mapper_enabled?: boolean;
    output_mapper?: Record<string, string>;
    payload_schema?: {
      fields: Array<{
        name: string;
        type: 'string' | 'integer' | 'number' | 'boolean' | 'array' | 'object';
        required: boolean;
        description: string;
      }>;
    };
    [key: string]: unknown;
  }>;
};

export const initialFormState: ApiServiceForm = {
  id: '',
  base_url: '',
  auth: {
    id: 'basic-auth',
    version: 'v1',
    type: 'basic',
    base_url: '',
    path: '',
    username: '',
    password: '',
    token: '',
    api_key: '',
    api_key_header: 'X-API-Key',
    additional_headers: [],
  },
  apis: [],
};

export const generateYaml = (data: ApiServiceForm) => {
  const authHeadersObj: Record<string, string> = {};
  data.auth.additional_headers.forEach((h) => {
    if (h.key && h.value) authHeadersObj[h.key] = h.value;
  });

  const serviceObj = {
    service: {
      id: data.id,
      base_url: data.base_url,
      auth: {
        id: data.auth.id,
        version: data.auth.version,
        type: data.auth.type,
        ...(data.auth.base_url && { base_url: data.auth.base_url }),
        ...(data.auth.path && { path: data.auth.path }),
        ...(data.auth.username && { username: data.auth.username }),
        ...(data.auth.password && { password: data.auth.password }),
        ...(data.auth.token && { token: data.auth.token }),
        ...(data.auth.api_key && { api_key: data.auth.api_key }),
        ...(data.auth.api_key_header && {
          api_key_header: data.auth.api_key_header,
        }),
        ...(Object.keys(authHeadersObj).length > 0 && {
          additional_headers: authHeadersObj,
        }),
      },
      apis: data.apis.map((api) => {
        const apiHeadersObj: Record<string, string> = {};
        api.additional_headers.forEach((h) => {
          if (h.key && h.value) apiHeadersObj[h.key] = h.value;
        });

        const backendQueryParamsObj: Record<string, unknown> = {};
        api.backend_query_params.forEach((p) => {
          if (p.key && p.value) backendQueryParamsObj[p.key] = p.value;
        });

        const outputMapperObj: Record<string, string> = {};
        if (api.output_mapper_enabled) {
          api.output_mapper.forEach((h) => {
            if (h.key && h.value) outputMapperObj[h.key] = h.value;
          });
        }

        const result: Record<string, unknown> = {
          id: api.id,
          version: api.version,
          path: api.path,
          backend_path: api.backend_path,
          method: api.method,
          ...(api.description && { description: api.description }),
          ...(Object.keys(apiHeadersObj).length > 0 && {
            additional_headers: apiHeadersObj,
          }),
          ...(Object.keys(backendQueryParamsObj).length > 0 && {
            backend_query_params: backendQueryParamsObj,
          }),
          output_mapper_enabled: api.output_mapper_enabled,
          ...(api.output_mapper_enabled &&
            Object.keys(outputMapperObj).length > 0 && {
              output_mapper: outputMapperObj,
            }),
        };

        // Add payload_schema for POST, PUT, PATCH methods
        if (
          ['POST', 'PUT', 'PATCH'].includes(api.method) &&
          api.payload_schema?.fields &&
          api.payload_schema.fields.length > 0
        ) {
          result.payload_schema = {
            fields: api.payload_schema.fields.map((field) => ({
              name: field.name,
              type: field.type,
              required: field.required,
              ...(field.description && { description: field.description }),
            })),
          };
        }

        return result;
      }),
    },
  };

  return yaml.dump(serviceObj);
};

export const parseYaml = (yamlStr: string): ApiServiceForm | null => {
  try {
    const parsed = yaml.load(yamlStr) as { service?: ParsedYamlService } | null;
    if (!parsed || !parsed.service) return null;

    const s = parsed.service;

    const authHeaders = s.auth?.additional_headers || {};
    const auth_additional_headers = Object.entries(authHeaders).map(([key, value]) => ({
      key,
      value: String(value),
    }));

    return {
      id: s.id || '',
      base_url: s.base_url || '',
      auth: {
        id: s.auth?.id || 'basic-auth',
        version: s.auth?.version || 'v1',
        type: (s.auth?.type as 'basic' | 'bearer' | 'api_key' | 'none') || 'basic',
        base_url: s.auth?.base_url || '',
        path: s.auth?.path || '',
        username: s.auth?.username || '',
        password: s.auth?.password || '',
        token: s.auth?.token || '',
        api_key: s.auth?.api_key || '',
        api_key_header: s.auth?.api_key_header || 'X-API-Key',
        additional_headers: auth_additional_headers,
      },
      apis: (s.apis || []).map((api) => {
        const apiHeaders = api.additional_headers || {};
        const api_additional_headers = Object.entries(apiHeaders).map(([key, value]) => ({
          key,
          value: String(value),
        }));

        const backendQueryParams = api.backend_query_params || {};
        const backend_query_params = Object.entries(backendQueryParams).map(([key, value]) => ({
          key,
          value: String(value),
        }));

        const outputMapper = api.output_mapper || {};
        const output_mapper = Object.entries(outputMapper).map(([key, value]) => ({
          key,
          value: String(value),
        }));

        const payload_schema = api.payload_schema?.fields
          ? {
              fields: api.payload_schema.fields.map((field) => ({
                name: field.name,
                type: field.type,
                required: field.required,
                description: field.description,
              })),
            }
          : { fields: [] };

        return {
          id: api.id || '',
          version: api.version || 'v1',
          path: api.path || '',
          backend_path: api.backend_path || '',
          method: (api.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH') || 'GET',
          description: api.description || '',
          additional_headers: api_additional_headers,
          backend_query_params: backend_query_params,
          output_mapper_enabled: api.output_mapper_enabled || false,
          output_mapper: output_mapper,
          payload_schema: payload_schema,
        };
      }),
    };
  } catch (e) {
    console.error('Error parsing YAML', e);
    return null;
  }
};

export const mapServiceToForm = (serviceData: ApiServiceItem): ApiServiceForm => {
  const authHeaders = serviceData.auth.additional_headers || {};
  const auth_additional_headers = Object.entries(authHeaders).map(([key, value]) => ({
    key,
    value: String(value),
  }));

  return {
    id: serviceData.service_id,
    base_url: serviceData.base_url,
    auth: {
      id: serviceData.auth.id,
      version: serviceData.auth.version,
      type: (serviceData.auth.type as 'basic' | 'bearer' | 'api_key' | 'none') || 'basic',
      base_url: serviceData.auth.base_url || '',
      path: serviceData.auth.path || '',
      username: serviceData.auth.username || '',
      password: serviceData.auth.password || '',
      token: serviceData.auth.token || '',
      api_key: serviceData.auth.api_key || '',
      api_key_header: serviceData.auth.api_key_header || 'X-API-Key',
      additional_headers: auth_additional_headers,
    },
    apis: (serviceData.apis || []).map((api) => {
      const apiHeaders = api.additional_headers || {};
      const api_additional_headers = Object.entries(apiHeaders).map(([key, value]) => ({
        key,
        value: String(value),
      }));

      const backendQueryParams = api.backend_query_params || {};
      const backend_query_params = Object.entries(backendQueryParams).map(([key, value]) => ({
        key,
        value: String(value),
      }));

      const outputMapper = api.output_mapper || {};
      const output_mapper = Object.entries(outputMapper).map(([key, value]) => ({
        key,
        value: String(value),
      }));

      const payload_schema = api.payload_schema?.fields
        ? {
            fields: api.payload_schema.fields.map((field) => ({
              name: field.name,
              type: field.type,
              required: field.required,
              description: field.description,
            })),
          }
        : { fields: [] };

      return {
        id: api.id,
        version: api.version,
        path: api.path,
        backend_path: api.backend_path || '',
        method: api.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH',
        description: api.description || '',
        additional_headers: api_additional_headers,
        backend_query_params: backend_query_params,
        output_mapper_enabled: api.output_mapper_enabled || false,
        output_mapper: output_mapper,
        payload_schema: payload_schema,
      };
    }),
  };
};
