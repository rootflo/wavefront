import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import DetailActions from '@app/components/DetailActions';
import MobileBackButton from '@app/components/MobileBackButton';
import PageTitle from '@app/components/PageTitle';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useDeleteApiService, useGetApiService, useUpdateApiService } from '@app/hooks';
import { formatAppName } from '@app/utils/string-formatting';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import clsx from 'clsx';
import { Plus, Trash2 } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import {
  ApiServiceForm,
  apiServiceFormSchema,
  generateYaml,
  initialFormState,
  mapServiceToForm,
  parseYaml,
} from './api-service-form';

const ApiServiceDetail: React.FC = () => {
  const [editing, setEditing] = useState(false);
  const [view, setView] = useState<'form' | 'yaml'>('form');
  const [yamlContent, setYamlContent] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const navigate = useNavigate();
  const { notifyError } = useNotifyStore();
  const updateApiService = useUpdateApiService(appId);
  const deleteApiService = useDeleteApiService(appId);

  const { data: service, isLoading: serviceLoading } = useGetApiService(appId, id);

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

  const handleSave = (data?: ApiServiceForm) => {
    if (!id || !appId) return;

    // Ensure we have the latest content based on current view
    const formValues = data || form.getValues();
    const finalYaml = view === 'form' ? generateYaml(formValues) : yamlContent;

    updateApiService.mutate(
      { serviceId: id, yamlContent: finalYaml },
      {
        onSuccess: () => {
          setYamlContent(finalYaml);
          const parsed = parseYaml(finalYaml);
          if (parsed) form.reset(parsed);
          setEditing(false);
        },
      }
    );
  };

  const handleDelete = () => {
    if (!id || !appId) return;
    deleteApiService.mutate(id, { onSuccess: () => navigate(`/apps/${appId}/api-services`) });
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
      description: '',
      additional_headers: [],
      backend_query_params: [],
      output_mapper_enabled: false,
      output_mapper: [],
      payload_schema: {
        fields: [],
      },
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

  const handleAddPayloadField = (apiIndex: number) => {
    const currentFields = form.getValues(`apis.${apiIndex}.payload_schema.fields`) || [];
    form.setValue(`apis.${apiIndex}.payload_schema.fields`, [
      ...currentFields,
      { name: '', type: 'string', required: false, description: '' },
    ]);
  };

  const handleRemovePayloadField = (apiIndex: number, fieldIndex: number) => {
    const currentFields = form.getValues(`apis.${apiIndex}.payload_schema.fields`) || [];
    form.setValue(
      `apis.${apiIndex}.payload_schema.fields`,
      currentFields.filter((_, i) => i !== fieldIndex)
    );
  };

  const handleCancelEdit = () => {
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
  };

  return (
    <div className="h-full bg-transparent px-4 pt-4 pb-[200px] sm:px-8 sm:pt-8">
      <PageBreadcrumb
        items={[
          { label: 'API Services', to: `/apps/${appId}/api-services` },
          { label: service?.name || service?.service_id || id, loading: serviceLoading },
        ]}
      />

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <MobileBackButton to={`/apps/${appId}/api-services`} label="Back to api services" />
            <PageTitle loading={serviceLoading}>{formatAppName(service?.name || service?.service_id)}</PageTitle>
          </div>
          <DetailActions
            editing={editing}
            onEdit={() => setEditing(true)}
            onDelete={() => setShowDeleteConfirm(true)}
            onSave={form.handleSubmit(handleSave)}
            onCancel={handleCancelEdit}
            saving={updateApiService.isPending}
          />
        </div>

        <div className="flex w-full flex-col gap-6">
          {/* Tabs */}
          <div className="border-frost-border flex border-b">
            <button
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                view === 'form' ? 'border-brand text-brand border-b-2' : 'frost-text-muted hover:text-frost-text'
              )}
              onClick={() => setView('form')}
            >
              Form View
            </button>
            <button
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                view === 'yaml' ? 'border-brand text-brand border-b-2' : 'frost-text-muted hover:text-frost-text'
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
                <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                  <h3 className="frost-text text-lg font-semibold">Service Details</h3>
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
                <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                  <h3 className="frost-text text-lg font-semibold">Authentication</h3>
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
                <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                  <div className="flex items-center justify-between">
                    <h3 className="frost-text text-lg font-semibold">API Endpoints</h3>
                    <Button type="button" onClick={handleAddApi} variant="outline" size="icon" disabled={!editing}>
                      <Plus />
                    </Button>
                  </div>

                  <div className="flex w-full flex-col gap-6">
                    {apisFieldArray.fields.map((field, index) => (
                      <div key={field.id} className="flex w-full gap-6">
                        <div
                          key={field.id}
                          className="frost-control ring-frost-border relative w-full rounded-lg border p-6 ring-1"
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

                          {/* API Description */}
                          <div className="mt-6 w-full">
                            <FormField
                              control={form.control}
                              name={`apis.${index}.description`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>Description (Optional)</FormLabel>
                                  <FormControl>
                                    <Input
                                      placeholder="e.g., Fetches all users from the system"
                                      disabled={!editing}
                                      {...field}
                                    />
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
                                (_header: unknown, hIndex: number) => (
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
                                (_param: unknown, pIndex: number) => (
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

                          {/* Payload Schema - Only for POST, PUT, PATCH */}
                          {['POST', 'PUT', 'PATCH'].includes(form.watch(`apis.${index}.method`)) && (
                            <div className="mt-6 w-full">
                              <div className="mb-4 flex items-center justify-between">
                                <Label className="text-sm font-medium">Payload Schema</Label>
                                <Button
                                  type="button"
                                  onClick={() => handleAddPayloadField(index)}
                                  variant="outline"
                                  size="icon"
                                  disabled={!editing}
                                >
                                  <Plus />
                                </Button>
                              </div>
                              <div className="flex w-full flex-col gap-3">
                                {(form.watch(`apis.${index}.payload_schema.fields`) || []).map(
                                  (_field: unknown, fIndex: number) => (
                                    <div key={fIndex} className="flex w-full gap-3">
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.payload_schema.fields.${fIndex}.name`}
                                        render={({ field }) => (
                                          <FormItem className="flex-1">
                                            <FormControl>
                                              <Input placeholder="Field Name" disabled={!editing} {...field} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.payload_schema.fields.${fIndex}.type`}
                                        render={({ field }) => (
                                          <FormItem className="flex-1">
                                            <Select
                                              onValueChange={field.onChange}
                                              value={field.value}
                                              disabled={!editing}
                                            >
                                              <FormControl>
                                                <SelectTrigger>
                                                  <SelectValue placeholder="Type" />
                                                </SelectTrigger>
                                              </FormControl>
                                              <SelectContent>
                                                <SelectItem value="string">String</SelectItem>
                                                <SelectItem value="integer">Integer</SelectItem>
                                                <SelectItem value="number">Number</SelectItem>
                                                <SelectItem value="boolean">Boolean</SelectItem>
                                                <SelectItem value="array">Array</SelectItem>
                                                <SelectItem value="object">Object</SelectItem>
                                              </SelectContent>
                                            </Select>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.payload_schema.fields.${fIndex}.required`}
                                        render={({ field }) => (
                                          <FormItem className="flex flex-row items-center space-y-0 space-x-2 pt-2">
                                            <FormControl>
                                              <Checkbox
                                                checked={field.value}
                                                onCheckedChange={field.onChange}
                                                disabled={!editing}
                                              />
                                            </FormControl>
                                            <FormLabel className="mb-0 text-xs">Required</FormLabel>
                                          </FormItem>
                                        )}
                                      />
                                      <FormField
                                        control={form.control}
                                        name={`apis.${index}.payload_schema.fields.${fIndex}.description`}
                                        render={({ field }) => (
                                          <FormItem className="flex-1">
                                            <FormControl>
                                              <Input placeholder="Description" disabled={!editing} {...field} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                      <Button
                                        type="button"
                                        onClick={() => handleRemovePayloadField(index, fIndex)}
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
                          )}

                          {/* Output Mapper */}
                          <div className="border-frost-border mt-6 w-full border-t pt-6">
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
                                  (_mapper: unknown, mIndex: number) => (
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
                      <div className="frost-text-muted py-8 text-center text-sm">
                        No endpoints added yet. Click "Add Endpoint" to start.
                      </div>
                    )}
                  </div>
                </div>
              </form>
            </Form>
          ) : (
            <div className="flex flex-col gap-4">
              <CodeEditor
                value={yamlContent}
                editable={editing}
                height="600px"
                extensions={[langs.yaml()]}
                onChange={(value: string) => setYamlContent(value)}
                className={clsx(
                  'frost-control ring-frost-border frost-text w-full rounded-lg border px-3 py-2 font-mono text-sm ring-1 outline-none',
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
