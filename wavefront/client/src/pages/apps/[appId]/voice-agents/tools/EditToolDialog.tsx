/* eslint-disable @typescript-eslint/no-explicit-any */
import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgentTool, ApiToolConfig } from '@app/types/tool';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;
const AUTH_TYPES = ['none', 'bearer', 'api_key', 'basic'] as const;

const editToolSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(255, 'Display name must be 255 characters or less'),
  description: z.string().min(1, 'Description is required'),
  // API Config fields
  method: z.enum(HTTP_METHODS).optional(),
  url: z.string().url('Must be a valid URL').optional(),
  timeout: z.number().min(1).max(300).optional(),
  auth_type: z.enum(AUTH_TYPES).optional(),
  auth_token: z.string().optional(),
  api_key_name: z.string().optional(),
  api_key_value: z.string().optional(),
  basic_username: z.string().optional(),
  basic_password: z.string().optional(),
  // Parameter schema as JSON string
  parameter_schema: z.string().optional(),
});

type EditToolInput = z.infer<typeof editToolSchema>;

interface EditToolDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  tool: VoiceAgentTool;
  onSuccess?: () => void;
}

const EditToolDialog: React.FC<EditToolDialogProps> = ({ isOpen, onOpenChange, tool, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loading, setLoading] = useState(false);

  const form = useForm<EditToolInput>({
    resolver: zodResolver(editToolSchema),
    defaultValues: {
      display_name: '',
      description: '',
      method: 'POST',
      url: '',
      timeout: 30,
      auth_type: 'none',
      auth_token: '',
      api_key_name: 'X-API-Key',
      api_key_value: '',
      basic_username: '',
      basic_password: '',
      parameter_schema: '',
    },
  });

  const watchAuthType = form.watch('auth_type');

  // Load tool data when dialog opens
  useEffect(() => {
    if (isOpen && tool) {
      const apiConfig = tool.config as ApiToolConfig;

      form.reset({
        display_name: tool.display_name,
        description: tool.description,
        method: apiConfig?.method || 'POST',
        url: apiConfig?.url || '',
        timeout: apiConfig?.timeout || 30,
        auth_type: apiConfig?.auth_type || 'none',
        auth_token: '',
        api_key_name: apiConfig?.auth_credentials?.key_name || 'X-API-Key',
        api_key_value: '',
        basic_username: apiConfig?.auth_credentials?.username || '',
        basic_password: '',
        parameter_schema: tool.parameter_schema ? JSON.stringify(tool.parameter_schema, null, 2) : '',
      });
    }
  }, [isOpen, tool, form]);

  const onSubmit = async (data: EditToolInput) => {
    setLoading(true);
    try {
      let config: any = {};
      let parameterSchema: any = undefined;

      if (tool.tool_type === 'api') {
        config = {
          method: data.method,
          url: data.url,
          timeout: data.timeout || 30,
          auth_type: data.auth_type || 'none',
        };

        // Only include auth_credentials if user provided NEW credentials
        if (data.auth_type === 'bearer' && data.auth_token && data.auth_token.trim()) {
          // User provided new bearer token
          config.auth_credentials = { token: data.auth_token };
        } else if (data.auth_type === 'api_key' && data.api_key_value && data.api_key_value.trim()) {
          // User provided new API key
          config.auth_credentials = {
            key_name: data.api_key_name || 'X-API-Key',
            key_value: data.api_key_value,
          };
        } else if (
          data.auth_type === 'basic' &&
          data.basic_username &&
          data.basic_password &&
          data.basic_username.trim() &&
          data.basic_password.trim()
        ) {
          // User provided new basic auth credentials
          config.auth_credentials = {
            username: data.basic_username,
            password: data.basic_password,
          };
        }
        // Otherwise: don't include auth_credentials at all - backend will preserve existing
      }

      // Parse parameter schema if provided
      if (data.parameter_schema && data.parameter_schema.trim()) {
        try {
          parameterSchema = JSON.parse(data.parameter_schema);
        } catch {
          notifyError('Invalid JSON in parameter schema');
          setLoading(false);
          return;
        }
      }

      await floConsoleService.toolService.updateTool(tool.id, {
        display_name: data.display_name.trim(),
        description: data.description.trim(),
        config,
        parameter_schema: parameterSchema,
      });

      notifySuccess('Tool updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update tool');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Tool</DialogTitle>
          <DialogDescription>Update tool configuration</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Basic Information</h3>

              <div className="rounded-md bg-gray-50 p-3">
                <div className="text-sm text-gray-600">Function Name (cannot be changed)</div>
                <div className="font-mono text-sm font-medium">{tool.name}</div>
              </div>

              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display Name*</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Weather API, Booking System" {...field} />
                    </FormControl>
                    <FormDescription>Human-readable name for the tool</FormDescription>
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
                    <FormDescription>The LLM uses this description to decide when to call this tool</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="rounded-md bg-gray-50 p-3">
                <div className="text-sm text-gray-600">Tool Type (cannot be changed)</div>
                <div className="font-medium uppercase">{tool.tool_type}</div>
              </div>
            </div>

            {/* API Configuration */}
            {tool.tool_type === 'api' && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">API Configuration</h3>

                <div className="grid grid-cols-2 gap-4">
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
                      <FormDescription>Full URL to the API endpoint</FormDescription>
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
                            placeholder="Enter new bearer token (leave blank to keep existing)"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {watchAuthType === 'api_key' && (
                  <div className="grid grid-cols-2 gap-4">
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
                              placeholder="Enter new API key (leave blank to keep existing)"
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
                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="basic_username"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Username</FormLabel>
                          <FormControl>
                            <Input placeholder="Enter new username (leave blank to keep existing)" {...field} />
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
                              placeholder="Enter new password (leave blank to keep existing)"
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
                    <FormDescription>JSON Schema defining the parameters this tool accepts</FormDescription>
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
                {loading ? 'Updating...' : 'Update Tool'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditToolDialog;
