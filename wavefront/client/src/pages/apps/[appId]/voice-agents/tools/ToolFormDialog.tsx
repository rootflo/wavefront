import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Textarea } from '@app/components/ui/textarea';
import { useCreateTool, useUpdateTool } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { ApiToolConfig, AppToolConfig, AuthType, ToolType, VoiceAgentTool } from '@app/types/tool';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useMemo } from 'react';
import { useParams } from 'react-router';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;
const AUTH_TYPES = ['none', 'bearer', 'api_key', 'basic'] as const;

// The name and type are fixed once a tool exists, so editing does not validate them
const buildSchema = (isEdit: boolean) =>
  z.object({
    name: isEdit
      ? z.string()
      : z
          .string()
          .min(1, 'Name is required')
          .max(100, 'Name must be 100 characters or less')
          .regex(/^[a-z_][a-z0-9_]*$/, 'Name must follow Python function naming (lowercase, underscores, no spaces)'),
    display_name: z.string().min(1, 'Display name is required').max(255, 'Display name must be 255 characters or less'),
    description: z.string().min(1, 'Description is required'),
    tool_type: z.enum(['api', 'python', 'app']),
    // API Config fields
    method: z.enum(HTTP_METHODS).optional(),
    url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    timeout: z.number().min(1).max(300).optional(),
    auth_type: z.enum(AUTH_TYPES).optional(),
    auth_token: z.string().optional(),
    api_key_name: z.string().optional(),
    api_key_value: z.string().optional(),
    basic_username: z.string().optional(),
    basic_password: z.string().optional(),
    // App Config fields
    ack_timeout_s: z.number().gt(0).max(30).optional(),
    speak_on_success: z.boolean().optional(),
    // Parameter schema as JSON string
    parameter_schema: z.string().optional(),
  });

type ToolInput = z.infer<ReturnType<typeof buildSchema>>;

/** Secrets are never returned by the API, so their fields always start empty. */
const toFormValues = (tool?: VoiceAgentTool): ToolInput => {
  const apiConfig = tool?.config as ApiToolConfig | undefined;
  const appConfig = tool?.config as AppToolConfig | undefined;
  return {
    name: tool?.name ?? '',
    display_name: tool?.display_name ?? '',
    description: tool?.description ?? '',
    tool_type: tool?.tool_type ?? 'api',
    method: apiConfig?.method || 'POST',
    url: apiConfig?.url || '',
    timeout: apiConfig?.timeout || 30,
    auth_type: apiConfig?.auth_type || 'none',
    auth_token: '',
    api_key_name: apiConfig?.auth_credentials?.key_name || 'X-API-Key',
    api_key_value: '',
    basic_username: apiConfig?.auth_credentials?.username || '',
    basic_password: '',
    ack_timeout_s: appConfig?.ack_timeout_s ?? 4,
    speak_on_success: appConfig?.speak_on_success ?? false,
    parameter_schema: tool?.parameter_schema ? JSON.stringify(tool.parameter_schema, null, 2) : '',
  };
};

/** Credentials typed into the form. Left blank when editing, the stored ones are kept. */
const authCredentialsFrom = (data: ToolInput): Record<string, string> | undefined => {
  if (data.auth_type === 'bearer' && data.auth_token?.trim()) {
    return { token: data.auth_token };
  }
  if (data.auth_type === 'api_key' && data.api_key_value?.trim()) {
    return { key_name: data.api_key_name || 'X-API-Key', key_value: data.api_key_value };
  }
  if (data.auth_type === 'basic' && data.basic_username?.trim() && data.basic_password?.trim()) {
    return { username: data.basic_username, password: data.basic_password };
  }
  return undefined;
};

const SUBMIT_LABEL = {
  create: { idle: 'Create Tool', busy: 'Creating...' },
  edit: { idle: 'Update Tool', busy: 'Updating...' },
};

interface ToolFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** The tool to edit; omit to create one. Render separate instances for create and edit. */
  tool?: VoiceAgentTool;
}

const ToolFormDialog: React.FC<ToolFormDialogProps> = ({ isOpen, onOpenChange, tool }) => {
  const { app } = useParams<{ app: string }>();
  const { notifyError } = useNotifyStore();
  const createTool = useCreateTool(app);
  const updateTool = useUpdateTool(app);
  const isEdit = !!tool;
  const loading = createTool.isPending || updateTool.isPending;

  const schema = useMemo(() => buildSchema(isEdit), [isEdit]);
  const form = useForm<ToolInput>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(tool),
  });

  const watchToolType = form.watch('tool_type');
  const watchAuthType = form.watch('auth_type');

  // Start from the tool being edited, or a blank form, each time the dialog opens
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(tool));
    }
  }, [isOpen, tool, form]);

  const onSubmit = (data: ToolInput) => {
    let config: ApiToolConfig | AppToolConfig = {};

    if (data.tool_type === 'api') {
      if (!isEdit && !data.url?.trim()) {
        notifyError('API URL is required');
        return;
      }
      config = {
        method: data.method ?? 'POST',
        url: data.url ?? '',
        timeout: data.timeout || 30,
        auth_type: (data.auth_type || 'none') as AuthType,
        auth_credentials: authCredentialsFrom(data),
      };
    } else if (data.tool_type === 'app') {
      config = {
        ack_timeout_s: data.ack_timeout_s ?? 4,
        speak_on_success: data.speak_on_success ?? false,
      };
    }

    // Parse parameter schema if provided
    let parameterSchema: Record<string, unknown> | undefined;
    if (data.parameter_schema?.trim()) {
      try {
        parameterSchema = JSON.parse(data.parameter_schema);
      } catch {
        notifyError('Invalid JSON in parameter schema');
        return;
      }
    }

    const fields = {
      display_name: data.display_name.trim(),
      description: data.description.trim(),
      config,
      parameter_schema: parameterSchema,
    };
    const close = () => onOpenChange(false);
    if (tool) {
      updateTool.mutate({ toolId: tool.id, data: fields }, { onSuccess: close });
    } else {
      createTool.mutate(
        { ...fields, name: data.name.trim(), tool_type: data.tool_type as ToolType },
        { onSuccess: close }
      );
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Tool' : 'Create Tool'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update tool configuration' : 'Create a new tool that voice agents can use during conversations'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Basic Information</h3>

              {isEdit ? (
                <div className="frost-glass border-frost-border rounded-md border p-3">
                  <div className="frost-text-muted text-sm">Function Name (cannot be changed)</div>
                  <div className="frost-text font-mono text-sm font-medium">{tool.name}</div>
                </div>
              ) : (
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Function Name*</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., get_weather, book_appointment" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display Name*</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Weather API, Booking System" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description*</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Describe what this tool does and when the LLM should use it"
                        rows={3}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {isEdit ? (
                <div className="frost-glass border-frost-border rounded-md border p-3">
                  <div className="frost-text-muted text-sm">Tool Type (cannot be changed)</div>
                  <div className="frost-text font-medium uppercase">{tool.tool_type}</div>
                </div>
              ) : (
                <FormField
                  control={form.control}
                  name="tool_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tool Type*</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select tool type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="api">API Tool</SelectItem>
                          <SelectItem value="app">App Tool</SelectItem>
                          <SelectItem value="python" disabled>
                            Python Tool (Coming Soon)
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

            {/* API Configuration */}
            {watchToolType === 'api' && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">API Configuration</h3>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="method"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>HTTP Method*</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {HTTP_METHODS.map((method) => (
                              <SelectItem key={method} value={method}>
                                {method}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="timeout"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Timeout (seconds)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value) || 30)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>API URL*</FormLabel>
                      <FormControl>
                        <Input placeholder="https://api.example.com/endpoint" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="auth_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Authentication Type</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          <SelectItem value="bearer">Bearer Token</SelectItem>
                          <SelectItem value="api_key">API Key</SelectItem>
                          <SelectItem value="basic">Basic Auth</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {watchAuthType === 'bearer' && (
                  <FormField
                    control={form.control}
                    name="auth_token"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Bearer Token</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder={
                              isEdit ? 'Enter new bearer token (leave blank to keep existing)' : 'Enter bearer token'
                            }
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {watchAuthType === 'api_key' && (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="api_key_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>API Key Header Name</FormLabel>
                          <FormControl>
                            <Input placeholder="X-API-Key" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="api_key_value"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>API Key Value</FormLabel>
                          <FormControl>
                            <Input
                              type="password"
                              placeholder={
                                isEdit ? 'Enter new API key (leave blank to keep existing)' : 'Enter API key'
                              }
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                )}

                {watchAuthType === 'basic' && (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="basic_username"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Username</FormLabel>
                          <FormControl>
                            <Input
                              placeholder={
                                isEdit ? 'Enter new username (leave blank to keep existing)' : 'Enter username'
                              }
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="basic_password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Password</FormLabel>
                          <FormControl>
                            <Input
                              type="password"
                              placeholder={
                                isEdit ? 'Enter new password (leave blank to keep existing)' : 'Enter password'
                              }
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                )}
              </div>
            )}

            {/* App Configuration */}
            {watchToolType === 'app' && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">App Configuration</h3>
                <p className="frost-text-muted text-sm">
                  Handled by the browser app — the agent emits an event instead of making an HTTP call.
                </p>

                <FormField
                  control={form.control}
                  name="ack_timeout_s"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Ack timeout (seconds)</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.5"
                          min={0.5}
                          max={30}
                          {...field}
                          value={field.value ?? ''}
                          onChange={(e) => field.onChange(e.target.value === '' ? undefined : e.target.valueAsNumber)}
                        />
                      </FormControl>
                      <p className="frost-text-muted text-xs">How long to wait for the app to acknowledge the event</p>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="speak_on_success"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-start gap-3 space-y-0 rounded-md border p-3">
                      <FormControl>
                        <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <div className="space-y-1 leading-none">
                        <Label className="cursor-pointer font-medium" onClick={() => field.onChange(!field.value)}>
                          Speak on success
                        </Label>
                        <p className="frost-text-muted text-xs">
                          Let the agent speak after a successful call. Off by default so the app can open the next turn.
                        </p>
                      </div>
                    </FormItem>
                  )}
                />
              </div>
            )}

            {/* Parameter Schema */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Parameter Schema (Optional)</h3>
              <FormField
                control={form.control}
                name="parameter_schema"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>JSON Schema</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder='{"type": "object", "properties": {"location": {"type": "string"}}}'
                        rows={6}
                        className="font-mono text-sm"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {SUBMIT_LABEL[isEdit ? 'edit' : 'create'][loading ? 'busy' : 'idle']}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default ToolFormDialog;
