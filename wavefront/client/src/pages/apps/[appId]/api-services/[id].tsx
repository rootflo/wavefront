import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetApiService } from '@app/hooks';
import { getApiServiceKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { ApiServiceItem } from '@app/types/api-service';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import clsx from 'clsx';
import yaml from 'js-yaml';
import { Plus, Trash2 } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';

const keyValuePairSchema = z.object({
  key: z.string(),
  value: z.string(),
});

const apiEndpointSchema = z.object({
  id: z.string(),
  version: z.string(),
  path: z.string(),
  backend_path: z.string(),
  method: z.enum(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']),
  additional_headers: z.array(keyValuePairSchema),
  backend_query_params: z.array(keyValuePairSchema),
  output_mapper_enabled: z.boolean(),
  output_mapper: z.array(keyValuePairSchema),
});

const apiServiceFormSchema = z.object({
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

type ApiServiceForm = z.infer<typeof apiServiceFormSchema>;

const initialFormState: ApiServiceForm = {
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

const ApiServiceDetail: React.FC = () => {
  const [editing, setEditing] = useState(false);
  const [view, setView] = useState<'form' | 'yaml'>('form');
  const [yamlContent, setYamlContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const { data: service } = useGetApiService(appId, id);

  const form = useForm<ApiServiceForm>({
    resolver: zodResolver(apiServiceFormSchema),
    defaultValues: initialFormState,
    mode: 'onChange',
  });

  const authHeadersFieldArray = useFieldArray({
    control: form.control,
    name: 'auth.additional_headers',
  });

  const apisFieldArray = useFieldArray({
    control: form.control,
    name: 'apis',
  });

  const generateYaml = (data: ApiServiceForm) => {
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

          const backendQueryParamsObj: Record<string, any> = {};
          api.backend_query_params.forEach((p) => {
            if (p.key && p.value) backendQueryParamsObj[p.key] = p.value;
          });

          const outputMapperObj: Record<string, string> = {};
          if (api.output_mapper_enabled) {
            api.output_mapper.forEach((h) => {
              if (h.key && h.value) outputMapperObj[h.key] = h.value;
            });
          }

          return {
            id: api.id,
            version: api.version,
            path: api.path,
            backend_path: api.backend_path,
            method: api.method,
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
        }),
      },
    };

    return yaml.dump(serviceObj);
  };

  const parseYaml = (yamlStr: string): ApiServiceForm | null => {
    try {
      const parsed: any = yaml.load(yamlStr);
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
        apis: (s.apis || []).map((api: any) => {
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

          return {
            id: api.id || '',
            version: api.version || 'v1',
            path: api.path || '',
            backend_path: api.backend_path || '',
            method: (api.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH') || 'GET',
            additional_headers: api_additional_headers,
            backend_query_params: backend_query_params,
            output_mapper_enabled: api.output_mapper_enabled || false,
            output_mapper: output_mapper,
          };
        }),
      };
    } catch (e) {
      console.error('Error parsing YAML', e);
      return null;
    }
  };

  const mapServiceToForm = (serviceData: ApiServiceItem): ApiServiceForm => {
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

        return {
          id: api.id,
          version: api.version,
          path: api.path,
          backend_path: api.backend_path || '',
          method: api.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH',
          additional_headers: api_additional_headers,
          backend_query_params: backend_query_params,
          output_mapper_enabled: api.output_mapper_enabled || false,
          output_mapper: output_mapper,
        };
      }),
    };
  };

  // Process service data when it loads
  useEffect(() => {
    if (!service) return;

    let content = service.yaml_content || '';
    let parsedForm: ApiServiceForm | null = null;

    if (content) {
      parsedForm = parseYaml(content);

      // If YAML exists but couldn't be parsed, fall back to mapping service data
      if (!parsedForm) {
        parsedForm = mapServiceToForm(service);
        notifyError('YAML could not be parsed. Showing form populated from service data instead.');
      }
    } else {
      // Fallback: map service object to form
      parsedForm = mapServiceToForm(service);
      // Generate YAML from the mapped form so the YAML view is also populated
      content = generateYaml(parsedForm);
    }

    setYamlContent(content);
    if (parsedForm) {
      form.reset(parsedForm);
    }
  }, [service, notifyError, form]);

  useEffect(() => {
    if (!appId) {
      navigate('/apps');
      return;
    }
  }, [appId, navigate]);

  // Sync Form -> YAML when switching to YAML view
  useEffect(() => {
    if (view === 'yaml' && editing) {
      const formValues = form.getValues();
      const generated = generateYaml(formValues);
      setYamlContent(generated);
    }
  }, [view, editing, form]);

  // Sync YAML -> Form when switching to Form view
  useEffect(() => {
    if (view === 'form' && yamlContent && editing) {
      const parsed = parseYaml(yamlContent);
      if (parsed) {
        form.reset(parsed);
      }
    }
  }, [view, editing, yamlContent, form]);

  const handleSave = async (data?: ApiServiceForm) => {
    if (!id || !appId) return;

    // Ensure we have the latest content based on current view
    const formValues = data || form.getValues();
    const finalYaml = view === 'form' ? generateYaml(formValues) : yamlContent;

    setSaving(true);
    try {
      await floConsoleService.apiServiceService.updateApiService(id, finalYaml);

      // Invalidate query to refetch updated data
      queryClient.invalidateQueries({
        queryKey: getApiServiceKey(appId || '', id || ''),
      });
      queryClient.invalidateQueries({ queryKey: ['api-services', appId] });

      setYamlContent(finalYaml);
      const parsed = parseYaml(finalYaml);
      if (parsed) form.reset(parsed);

      setEditing(false);
      notifySuccess('API Service updated successfully');
    } catch (error: any) {
      console.error('Error updating API service:', error);
      const errorMessage = error?.response?.data?.meta?.error || error?.message || 'Failed to update API service';
      notifyError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || !appId) return;

    try {
      await floConsoleService.apiServiceService.deleteApiService(id);
      notifySuccess('API Service deleted successfully');
      navigate(`/apps/${appId}/api-services`);
    } catch (error) {
      console.error('Error deleting API service:', error);
      notifyError('Failed to delete API service');
    }
  };

  const handleAddHeader = () => {
    authHeadersFieldArray.append({ key: '', value: '' });
  };

  const handleRemoveHeader = (index: number) => {
    authHeadersFieldArray.remove(index);
  };

  const handleAddApi = () => {
    apisFieldArray.append({
      id: '',
      version: 'v1',
      path: '',
      backend_path: '',
      method: 'GET',
      additional_headers: [],
      backend_query_params: [],
      output_mapper_enabled: false,
      output_mapper: [],
    });
  };

  const handleRemoveApi = (index: number) => {
    apisFieldArray.remove(index);
  };

  const handleAddApiHeader = (apiIndex: number) => {
    const currentHeaders = form.getValues(`apis.${apiIndex}.additional_headers`) || [];
    form.setValue(`apis.${apiIndex}.additional_headers`, [...currentHeaders, { key: '', value: '' }]);
  };

  const handleRemoveApiHeader = (apiIndex: number, headerIndex: number) => {
    const currentHeaders = form.getValues(`apis.${apiIndex}.additional_headers`) || [];
    form.setValue(
      `apis.${apiIndex}.additional_headers`,
      currentHeaders.filter((_, i) => i !== headerIndex)
    );
  };

  const handleAddBackendQueryParam = (apiIndex: number) => {
    const currentParams = form.getValues(`apis.${apiIndex}.backend_query_params`) || [];
    form.setValue(`apis.${apiIndex}.backend_query_params`, [...currentParams, { key: '', value: '' }]);
  };

  const handleRemoveBackendQueryParam = (apiIndex: number, paramIndex: number) => {
    const currentParams = form.getValues(`apis.${apiIndex}.backend_query_params`) || [];
    form.setValue(
      `apis.${apiIndex}.backend_query_params`,
      currentParams.filter((_, i) => i !== paramIndex)
    );
  };

  const handleAddOutputMapper = (apiIndex: number) => {
    const currentMappers = form.getValues(`apis.${apiIndex}.output_mapper`) || [];
    form.setValue(`apis.${apiIndex}.output_mapper`, [...currentMappers, { key: '', value: '' }]);
  };

  const handleRemoveOutputMapper = (apiIndex: number, mapperIndex: number) => {
    const currentMappers = form.getValues(`apis.${apiIndex}.output_mapper`) || [];
    form.setValue(
      `apis.${apiIndex}.output_mapper`,
      currentMappers.filter((_, i) => i !== mapperIndex)
    );
  };

  return (
    <div className="h-full bg-white px-8 pt-8 pb-[200px]">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${appId}/api-services`)}
                className="hover:text-foreground cursor-pointer"
              >
                API Services
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{service?.name || service?.service_id || id}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{service?.name || service?.service_id}</p>
          <div className="flex gap-4">
            {editing ? (
              <>
                <Button onClick={form.handleSubmit(handleSave)} loading={saving}>
                  Save
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditing(false);
                    // Revert changes by resetting form to service data
                    if (service) {
                      const parsed = service.yaml_content ? parseYaml(service.yaml_content) : mapServiceToForm(service);
                      if (parsed) {
                        form.reset(parsed);
                        const yaml = generateYaml(parsed);
                        setYamlContent(yaml);
                      }
                    }
                  }}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              Delete
            </Button>
          </div>
        </div>

        <div className="flex w-full flex-col gap-6">
          {/* Tabs */}
          <div className="flex border-b border-gray-200">
            <button
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                view === 'form' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'
              )}
              onClick={() => setView('form')}
            >
              Form View
            </button>
            <button
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                view === 'yaml' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'
              )}
              onClick={() => setView('yaml')}
            >
              YAML View
            </button>
          </div>

          {view === 'form' ? (
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(handleSave)}
                className={clsx('flex w-full flex-col gap-8', !editing && 'pointer-events-none opacity-80')}
              >
                {/* Service Details */}
                <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
                  <h3 className="text-lg font-semibold text-gray-900">Service Details</h3>
                  <div className="grid w-full gap-6 lg:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Service ID</FormLabel>
                          <FormControl>
                            <Input placeholder="e.g., my-service-v1" disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="base_url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Base URL</FormLabel>
                          <FormControl>
                            <Input placeholder="https://api.example.com" disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                {/* Authentication */}
                <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
                  <h3 className="text-lg font-semibold text-gray-900">Authentication</h3>
                  <div className="grid w-full gap-6 lg:grid-cols-4">
                    <FormField
                      control={form.control}
                      name="auth.id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Auth ID</FormLabel>
                          <FormControl>
                            <Input disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="auth.type"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Type</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value} disabled={!editing}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select auth type" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="basic">Basic Auth</SelectItem>
                              <SelectItem value="bearer">Bearer Token</SelectItem>
                              <SelectItem value="api_key">API Key</SelectItem>
                              <SelectItem value="none">None</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="auth.version"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Version</FormLabel>
                          <FormControl>
                            <Input placeholder="v1" disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="auth.base_url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Auth Base URL (Optional)</FormLabel>
                          <FormControl>
                            <Input placeholder="Override service base URL" disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="auth.path"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Auth Path (Optional)</FormLabel>
                          <FormControl>
                            <Input placeholder="/auth/token" disabled={!editing} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {form.watch('auth.type') === 'basic' && (
                      <>
                        <FormField
                          control={form.control}
                          name="auth.username"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Username</FormLabel>
                              <FormControl>
                                <Input disabled={!editing} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="auth.password"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Password</FormLabel>
                              <FormControl>
                                <Input type="password" disabled={!editing} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </>
                    )}
                    {form.watch('auth.type') === 'bearer' && (
                      <FormField
                        control={form.control}
                        name="auth.token"
                        render={({ field }) => (
                          <FormItem className="lg:col-span-2">
                            <FormLabel>Token</FormLabel>
                            <FormControl>
                              <Input disabled={!editing} {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                    {form.watch('auth.type') === 'api_key' && (
                      <>
                        <FormField
                          control={form.control}
                          name="auth.api_key"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>API Key</FormLabel>
                              <FormControl>
                                <Input disabled={!editing} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="auth.api_key_header"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Header Name</FormLabel>
                              <FormControl>
                                <Input placeholder="X-API-Key" disabled={!editing} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </>
                    )}
                  </div>

                  {/* Additional Headers */}
                  <div className="mt-4 w-full">
                    <div className="mb-4 flex items-center justify-between">
                      <Label className="text-sm font-medium">Additional Headers</Label>
                      <Button type="button" onClick={handleAddHeader} variant="outline" size="icon" disabled={!editing}>
                        <Plus />
                      </Button>
                    </div>
                    <div className="flex w-full flex-col gap-3">
                      {authHeadersFieldArray.fields.map((field, index) => (
                        <div key={field.id} className="flex w-full gap-3">
                          <FormField
                            control={form.control}
                            name={`auth.additional_headers.${index}.key`}
                            render={({ field }) => (
                              <FormItem className="flex-1">
                                <FormControl>
                                  <Input placeholder="Header Key" disabled={!editing} {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name={`auth.additional_headers.${index}.value`}
                            render={({ field }) => (
                              <FormItem className="flex-1">
                                <FormControl>
                                  <Input placeholder="Header Value" disabled={!editing} {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <Button
                            type="button"
                            onClick={() => handleRemoveHeader(index)}
                            variant="outline"
                            size="icon"
                            disabled={!editing}
                          >
                            <Trash2 color="#DD5252" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* APIs */}
                <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-gray-900">API Endpoints</h3>
                    <Button type="button" onClick={handleAddApi} variant="outline" size="icon" disabled={!editing}>
                      <Plus />
                    </Button>
                  </div>

                  <div className="flex w-full flex-col gap-6">
                    {apisFieldArray.fields.map((field, index) => (
                      <div key={field.id} className="flex w-full gap-6">
                        <div
                          key={field.id}
                          className="relative w-full rounded-lg border border-gray-200 bg-gray-50 p-6"
                        >
                          <div className="grid w-full gap-6 lg:grid-cols-3">
                            <FormField
                              control={form.control}
                              name={`apis.${index}.id`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Endpoint ID</FormLabel>
                                  <FormControl>
                                    <Input placeholder="e.g., get-users" disabled={!editing} {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            <FormField
                              control={form.control}
                              name={`apis.${index}.method`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Method</FormLabel>
                                  <Select onValueChange={field.onChange} value={field.value} disabled={!editing}>
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue placeholder="Select method" />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="GET">GET</SelectItem>
                                      <SelectItem value="POST">POST</SelectItem>
                                      <SelectItem value="PUT">PUT</SelectItem>
                                      <SelectItem value="DELETE">DELETE</SelectItem>
                                      <SelectItem value="PATCH">PATCH</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            <FormField
                              control={form.control}
                              name={`apis.${index}.version`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Version</FormLabel>
                                  <FormControl>
                                    <Input placeholder="v1" disabled={!editing} {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            <FormField
                              control={form.control}
                              name={`apis.${index}.path`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Path</FormLabel>
                                  <FormControl>
                                    <Input placeholder="/api/v1/users" disabled={!editing} {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            <FormField
                              control={form.control}
                              name={`apis.${index}.backend_path`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Backend Path</FormLabel>
                                  <FormControl>
                                    <Input placeholder="users/all" disabled={!editing} {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>

                          {/* API Additional Headers */}
                          <div className="mt-6 w-full">
                            <div className="mb-4 flex items-center justify-between">
                              <Label className="text-sm font-medium">Additional Headers</Label>
                              <Button
                                type="button"
                                onClick={() => handleAddApiHeader(index)}
                                variant="outline"
                                size="icon"
                                disabled={!editing}
                              >
                                <Plus />
                              </Button>
                            </div>
                            <div className="flex w-full flex-col gap-3">
                              {(form.watch(`apis.${index}.additional_headers`) || []).map(
                                (_header: any, hIndex: number) => (
                                  <div key={hIndex} className="flex w-full gap-3">
                                    <FormField
                                      control={form.control}
                                      name={`apis.${index}.additional_headers.${hIndex}.key`}
                                      render={({ field }) => (
                                        <FormItem className="flex-1">
                                          <FormControl>
                                            <Input placeholder="Key" disabled={!editing} {...field} />
                                          </FormControl>
                                          <FormMessage />
                                        </FormItem>
                                      )}
                                    />
                                    <FormField
                                      control={form.control}
                                      name={`apis.${index}.additional_headers.${hIndex}.value`}
                                      render={({ field }) => (
                                        <FormItem className="flex-1">
                                          <FormControl>
                                            <Input placeholder="Value" disabled={!editing} {...field} />
                                          </FormControl>
                                          <FormMessage />
                                        </FormItem>
                                      )}
                                    />
                                    <Button
                                      type="button"
                                      onClick={() => handleRemoveApiHeader(index, hIndex)}
                                      variant="outline"
                                      size="icon"
                                      disabled={!editing}
                                    >
                                      <Trash2 color="#DD5252" />
                                    </Button>
                                  </div>
                                )
                              )}
                            </div>
                          </div>

                          {/* Backend Query Params */}
                          <div className="mt-6 w-full">
                            <div className="mb-4 flex items-center justify-between">
                              <Label className="text-sm font-medium">Backend Query Params</Label>
                              <Button
                                type="button"
                                onClick={() => handleAddBackendQueryParam(index)}
                                variant="outline"
                                size="icon"
                                disabled={!editing}
                              >
                                <Plus />
                              </Button>
                            </div>
                            <div className="flex w-full flex-col gap-3">
                              {(form.watch(`apis.${index}.backend_query_params`) || []).map(
                                (_param: any, pIndex: number) => (
                                  <div key={pIndex} className="flex w-full gap-3">
                                    <FormField
                                      control={form.control}
                                      name={`apis.${index}.backend_query_params.${pIndex}.key`}
                                      render={({ field }) => (
                                        <FormItem className="flex-1">
                                          <FormControl>
                                            <Input placeholder="Key" disabled={!editing} {...field} />
                                          </FormControl>
                                          <FormMessage />
                                        </FormItem>
                                      )}
                                    />
                                    <FormField
                                      control={form.control}
                                      name={`apis.${index}.backend_query_params.${pIndex}.value`}
                                      render={({ field }) => (
                                        <FormItem className="flex-1">
                                          <FormControl>
                                            <Input placeholder="Value" disabled={!editing} {...field} />
                                          </FormControl>
                                          <FormMessage />
                                        </FormItem>
                                      )}
                                    />
                                    <Button
                                      type="button"
                                      onClick={() => handleRemoveBackendQueryParam(index, pIndex)}
                                      variant="outline"
                                      size="icon"
                                      disabled={!editing}
                                    >
                                      <Trash2 color="#DD5252" />
                                    </Button>
                                  </div>
                                )
                              )}
                            </div>
                          </div>

                          {/* Output Mapper */}
                          <div className="mt-6 w-full border-t border-gray-200 pt-6">
                            <div className="mb-4 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <FormField
                                  control={form.control}
                                  name={`apis.${index}.output_mapper_enabled`}
                                  render={({ field }) => (
                                    <FormItem className="flex flex-row items-center space-y-0 space-x-2">
                                      <FormControl>
                                        <Checkbox
                                          checked={field.value}
                                          onCheckedChange={field.onChange}
                                          disabled={!editing}
                                        />
                                      </FormControl>
                                      <FormLabel className="mb-0 cursor-pointer">Enable Output Mapper</FormLabel>
                                    </FormItem>
                                  )}
                                />
                              </div>
                              {form.watch(`apis.${index}.output_mapper_enabled`) && (
                                <Button
                                  type="button"
                                  onClick={() => handleAddOutputMapper(index)}
                                  variant="outline"
                                  size="icon"
                                  disabled={!editing}
                                >
                                  <Plus />
                                </Button>
                              )}
                            </div>

                            {form.watch(`apis.${index}.output_mapper_enabled`) && (
                              <div className="flex w-full flex-col gap-3">
                                {(form.watch(`apis.${index}.output_mapper`) || []).map(
                                  (_mapper: any, mIndex: number) => (
                                    <div key={mIndex} className="flex w-full gap-3">
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.output_mapper.${mIndex}.key`}
                                        render={({ field }) => (
                                          <FormItem className="flex-1">
                                            <FormControl>
                                              <Input placeholder="Source Field" disabled={!editing} {...field} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.output_mapper.${mIndex}.value`}
                                        render={({ field }) => (
                                          <FormItem className="flex-1">
                                            <FormControl>
                                              <Input placeholder="Target Field" disabled={!editing} {...field} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                      <Button
                                        type="button"
                                        onClick={() => handleRemoveOutputMapper(index, mIndex)}
                                        variant="outline"
                                        size="icon"
                                        disabled={!editing}
                                      >
                                        <Trash2 color="#DD5252" />
                                      </Button>
                                    </div>
                                  )
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                        <Button
                          type="button"
                          onClick={() => handleRemoveApi(index)}
                          variant="outline"
                          size="icon"
                          disabled={!editing}
                        >
                          <Trash2 color="#DD5252" />
                        </Button>
                      </div>
                    ))}
                    {apisFieldArray.fields.length === 0 && (
                      <div className="py-8 text-center text-sm text-gray-500">
                        No endpoints added yet. Click "Add Endpoint" to start.
                      </div>
                    )}
                  </div>
                </div>
              </form>
            </Form>
          ) : (
            <div className="flex flex-col gap-4">
              <CodeMirror
                value={yamlContent}
                editable={editing}
                height="600px"
                extensions={[langs.yaml()]}
                onChange={(value: string) => setYamlContent(value)}
                theme="dark"
                className={clsx(
                  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-black outline-none',
                  !editing && 'pointer-events-none opacity-80'
                )}
                placeholder="Enter your API service YAML configuration..."
              />
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={showDeleteConfirm}
        title="Delete API Service"
        message="Are you sure you want to delete this API service? This action cannot be undone."
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
};

export default ApiServiceDetail;
