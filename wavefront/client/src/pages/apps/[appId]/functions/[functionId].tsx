import floConsoleService from '@app/api';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { useGetMessageProcessor } from '@app/hooks';
import { getMessageProcessorKey, getMessageProcessorsKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';

const functionFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  yaml_content: z.string().min(1, 'YAML configuration is required'),
});

type FunctionForm = z.infer<typeof functionFormSchema>;

const FunctionDetail: React.FC = () => {
  const { app: appId, functionId } = useParams<{ app: string; functionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  // Fetch message processor
  const { data: processor } = useGetMessageProcessor(appId, functionId);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Execution state
  const [executionInput, setExecutionInput] = useState('{}');
  const [executionContext, setExecutionContext] = useState('{}');
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<unknown>(null);

  const form = useForm<FunctionForm>({
    resolver: zodResolver(functionFormSchema),
    defaultValues: {
      name: '',
      description: '',
      yaml_content: '',
    },
    mode: 'onChange',
  });

  // Update form fields when processor loads
  useEffect(() => {
    if (processor) {
      form.reset({
        name: processor.name,
        description: processor.description || '',
        yaml_content: processor.yaml_content || '',
      });
    }
  }, [processor, form]);

  const handleSave = async (data: FunctionForm) => {
    if (!functionId) return;

    setSaving(true);
    try {
      const response = await floConsoleService.messageProcessorService.updateMessageProcessor(functionId, {
        name: data.name.trim(),
        description: data.description?.trim() || undefined,
        yaml_content: data.yaml_content.trim(),
      });

      if (response.data?.data) {
        // Invalidate query to refetch updated data
        queryClient.invalidateQueries({ queryKey: getMessageProcessorKey(appId || '', functionId || '') });
        queryClient.invalidateQueries({ queryKey: getMessageProcessorsKey(appId || '') });
        setEditing(false);
        notifySuccess('Function updated successfully');
      } else {
        notifyError(response.data?.meta?.error || 'Failed to update message processor');
      }
    } catch (error: unknown) {
      console.error('Error updating function:', error);
      notifyError('Failed to update function');
    } finally {
      setSaving(false);
    }
  };

  const handleExecute = async () => {
    if (!functionId) return;

    let inputData: Record<string, unknown> = {};
    let context: Record<string, unknown> = {};

    try {
      inputData = JSON.parse(executionInput) as Record<string, unknown>;
    } catch {
      notifyError('Invalid JSON in input data');
      return;
    }

    try {
      if (executionContext.trim()) {
        context = JSON.parse(executionContext) as Record<string, unknown>;
      }
    } catch {
      notifyError('Invalid JSON in execution context');
      return;
    }

    setExecuting(true);
    setExecutionResult(null);

    try {
      const response = await floConsoleService.messageProcessorService.executeMessageProcessor(functionId, {
        input_data: inputData,
        execution_context: Object.keys(context).length > 0 ? context : undefined,
      });

      if (response.data?.meta?.status === 'success') {
        setExecutionResult(response.data.data?.result);
        notifySuccess('Function executed successfully');
      } else {
        notifyError(response.data?.meta?.error || 'Failed to execute function');
      }
    } catch (error: unknown) {
      console.error('Error executing function:', error);
    } finally {
      setExecuting(false);
    }
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
                onClick={() => navigate(`/apps/${appId}/functions`)}
                className="hover:text-foreground cursor-pointer"
              >
                Functions
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{processor?.name || functionId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{processor?.name || functionId}</p>
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
                    // Revert changes by resetting form to processor data
                    if (processor) {
                      form.reset({
                        name: processor.name,
                        description: processor.description || '',
                        yaml_content: processor.yaml_content || '',
                      });
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
          </div>
        </div>

        <div className="grid w-full gap-6 lg:grid-cols-2">
          {/* Left Column: Details and YAML */}
          <div className="flex w-full flex-col gap-6">
            <Form {...form}>
              <form onSubmit={form.handleSubmit(handleSave)} className="flex w-full flex-col gap-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Name <span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input disabled={!editing} {...field} />
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
                      <FormLabel>Description</FormLabel>
                      <FormControl>
                        <Input disabled={!editing} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="yaml_content"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        YAML Configuration <span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <div className="rounded-lg border border-gray-300">
                          <CodeMirror
                            value={field.value}
                            height="400px"
                            extensions={[langs.yaml()]}
                            onChange={field.onChange}
                            theme="dark"
                            editable={editing}
                          />
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </form>
            </Form>
          </div>

          {/* Right Column: Execution */}
          <div className="flex h-full w-full flex-col gap-6">
            <div className="flex h-full w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="text-lg font-semibold text-gray-900">Execute Function</h3>

              <div className="flex h-full flex-col gap-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="inputData" className="block pb-2 text-sm font-medium text-gray-700">
                      Input Data (JSON) <span className="text-red-500">*</span>
                    </label>
                    <div className="rounded-lg border border-gray-300">
                      <CodeMirror
                        value={executionInput}
                        height="150px"
                        extensions={[langs.json()]}
                        onChange={(value) => setExecutionInput(value)}
                        theme="dark"
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="executionContext" className="block pb-2 text-sm font-medium text-gray-700">
                      Execution Context (optional)
                    </label>
                    <div className="rounded-lg border border-gray-300">
                      <CodeMirror
                        value={executionContext}
                        height="150px"
                        extensions={[langs.json()]}
                        onChange={(value) => setExecutionContext(value)}
                        theme="dark"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex flex-1 flex-col">
                  <label className="block pb-2 text-sm font-medium text-gray-700">Result</label>
                  <div className="flex-1 rounded-lg">
                    <CodeMirror
                      value={JSON.stringify(executionResult, null, 2)}
                      extensions={[langs.json()]}
                      height="100%"
                      editable={false}
                      theme="dark"
                      className="h-full"
                    />
                  </div>
                </div>

                <Button onClick={handleExecute} loading={executing}>
                  Execute
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FunctionDetail;
