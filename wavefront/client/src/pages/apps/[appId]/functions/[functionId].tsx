import floConsoleService from '@app/api';
import DetailActions from '@app/components/DetailActions';
import MobileBackButton from '@app/components/MobileBackButton';
import PageTitle from '@app/components/PageTitle';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { useGetMessageProcessor, useUpdateMessageProcessor } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useParams } from 'react-router';
import { z } from 'zod';
import { formatAppName } from '@app/lib/utils';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const functionFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  yaml_content: z.string().min(1, 'YAML configuration is required'),
});

type FunctionForm = z.infer<typeof functionFormSchema>;

const FunctionDetail: React.FC = () => {
  const { app: appId, functionId } = useParams<{ app: string; functionId: string }>();
  const updateMessageProcessor = useUpdateMessageProcessor(appId);
  const { notifySuccess, notifyError } = useNotifyStore();

  // Fetch message processor
  const { data: processor, isLoading: processorLoading } = useGetMessageProcessor(appId, functionId);

  const [editing, setEditing] = useState(false);

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

  const handleSave = (data: FunctionForm) => {
    if (!functionId) return;

    updateMessageProcessor.mutate(
      {
        processorId: functionId,
        data: {
          name: data.name.trim(),
          description: data.description?.trim() || undefined,
          yaml_content: data.yaml_content.trim(),
        },
      },
      { onSuccess: () => setEditing(false) }
    );
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

  const handleCancelEdit = () => {
    setEditing(false);
    // Revert changes by resetting form to processor data
    if (processor) {
      form.reset({
        name: processor.name,
        description: processor.description || '',
        yaml_content: processor.yaml_content || '',
      });
    }
  };

  return (
    <div className="h-full bg-transparent px-4 pt-4 pb-[200px] sm:px-8 sm:pt-8">
      <PageBreadcrumb
        items={[
          { label: 'Functions', to: `/apps/${appId}/functions` },
          { label: processor?.name || functionId, loading: processorLoading },
        ]}
      />

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <MobileBackButton to={`/apps/${appId}/functions`} label="Back to functions" />
            <PageTitle loading={processorLoading}>{formatAppName(processor?.name || functionId)}</PageTitle>
          </div>
          <DetailActions
            editing={editing}
            onEdit={() => setEditing(true)}
            onSave={form.handleSubmit(handleSave)}
            onCancel={handleCancelEdit}
            saving={updateMessageProcessor.isPending}
          />
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
                        <div className="frost-control ring-frost-border overflow-hidden rounded-lg border ring-1">
                          <CodeEditor
                            value={field.value}
                            height="400px"
                            extensions={[langs.yaml()]}
                            onChange={field.onChange}
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
            <div className="frost-panel ring-frost-border flex h-full w-full flex-col gap-6 rounded-lg border p-4 ring-1">
              <h3 className="frost-text text-lg font-semibold">Execute Function</h3>

              <div className="flex h-full flex-col gap-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="inputData" className="frost-text block pb-2 text-sm font-medium">
                      Input Data (JSON) <span className="text-red-500">*</span>
                    </label>
                    <div className="frost-control ring-frost-border overflow-hidden rounded-lg border ring-1">
                      <CodeEditor
                        value={executionInput}
                        height="150px"
                        extensions={[langs.json()]}
                        onChange={(value) => setExecutionInput(value)}
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="executionContext" className="frost-text block pb-2 text-sm font-medium">
                      Execution Context (optional)
                    </label>
                    <div className="frost-control ring-frost-border overflow-hidden rounded-lg border ring-1">
                      <CodeEditor
                        value={executionContext}
                        height="150px"
                        extensions={[langs.json()]}
                        onChange={(value) => setExecutionContext(value)}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex flex-1 flex-col">
                  <label className="frost-text block pb-2 text-sm font-medium">Result</label>
                  <div className="frost-control ring-frost-border flex-1 overflow-hidden rounded-lg border ring-1">
                    <CodeEditor
                      value={JSON.stringify(executionResult, null, 2)}
                      extensions={[langs.json()]}
                      height="100%"
                      editable={false}
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
