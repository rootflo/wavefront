import { describe, expect, it } from 'vitest';
import { ApiServiceForm, generateYaml, parseYaml } from './api-service-form';

const service: ApiServiceForm = {
  id: 'billing',
  base_url: 'https://billing.example.com',
  auth: {
    id: 'billing-auth',
    version: 'v1',
    type: 'bearer',
    base_url: 'https://auth.example.com',
    path: '/token',
    username: '',
    password: '',
    token: 'secret-token',
    api_key: '',
    api_key_header: 'X-API-Key',
    additional_headers: [{ key: 'X-Tenant', value: 'acme' }],
  },
  apis: [
    {
      id: 'create-invoice',
      version: 'v1',
      path: '/invoices',
      backend_path: '/v2/invoices',
      method: 'POST',
      description: 'Create an invoice',
      additional_headers: [{ key: 'Accept', value: 'application/json' }],
      backend_query_params: [{ key: 'expand', value: 'lines' }],
      output_mapper_enabled: true,
      output_mapper: [{ key: 'total', value: '$.amount.total' }],
      payload_schema: {
        fields: [{ name: 'customer_id', type: 'string', required: true, description: 'Who to bill' }],
      },
    },
  ],
};

describe('API service YAML', () => {
  it('reads back what it writes', () => {
    expect(parseYaml(generateYaml(service))).toEqual(service);
  });

  it('writes a payload schema only for methods that send a body', () => {
    const asGet = { ...service, apis: [{ ...service.apis[0], method: 'GET' as const }] };
    expect(generateYaml(asGet)).not.toContain('payload_schema');
  });

  it('rejects YAML without a service', () => {
    expect(parseYaml('other: true')).toBeNull();
    expect(parseYaml('')).toBeNull();
  });
});
