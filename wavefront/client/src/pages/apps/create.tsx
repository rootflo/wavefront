import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useNotifyStore } from '@app/store';
import { CreateAppRequest } from '@app/types/app';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { createAppSchema } from './schemas';
import { Checkbox } from '@app/components/ui/checkbox';
import { appEnv } from '@app/config/env';

type TCreateAppInputSchema = z.infer<typeof createAppSchema>;

const CreateApp: React.FC = () => {
  const navigate = useNavigate();
  const { notifySuccess } = useNotifyStore();

  const [creating, setCreating] = useState(false);
  const [pollingAppId, setPollingAppId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const form = useForm<TCreateAppInputSchema>({
    resolver: zodResolver(createAppSchema),
    defaultValues: {
      deployment_type: 'manual',
    },
  });

  const deploymentType = form.watch('deployment_type');

  // Polling function to check app status
  const pollAppStatus = useCallback(
    async (appId: string) => {
      try {
        const { data } = await floConsoleService.appService.getAppStatus(appId);
        if (data.data?.status === 'success') {
          // Clear polling interval
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setPollingAppId(null);
          setCreating(false);
          notifySuccess('App created successfully');
          navigate('/apps');
        }
      } catch (error) {
        console.error('Error polling app status:', error);
        // Stop polling on error
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setPollingAppId(null);
        setCreating(false);
      }
    },
    [navigate]
  );

  // Effect to handle polling
  useEffect(() => {
    if (pollingAppId && deploymentType === 'auto') {
      // Start polling immediately
      pollAppStatus(pollingAppId);

      // Set up interval for every 5 seconds
      pollingIntervalRef.current = setInterval(() => {
        pollAppStatus(pollingAppId);
      }, 5000);
    }

    // Cleanup function
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [pollingAppId, pollAppStatus, deploymentType]);

  const appCreationSubmit = async (formData: TCreateAppInputSchema) => {
    setCreating(true);
    try {
      // Transform form data to match CreateAppRequest type
      const appData: CreateAppRequest = {
        app_name: formData.app_name,
        deployment_type: formData.deployment_type,
        public_url: formData.public_url,
        private_url: formData.private_url,
      };

      const response = await floConsoleService.appService.createApp(appData);

      if (response.data?.data?.app.status === 'in_progress') {
        // Start polling for status updates only if deployment type is auto
        if (formData.deployment_type === 'auto') {
          setPollingAppId(response.data.data.app.id);
        } else {
          // For manual deployment, just show success
          setCreating(false);
          notifySuccess('App created successfully');
          navigate('/apps');
        }
      } else if (response.data?.data?.app.status === 'success') {
        // If already successful, show success immediately
        setCreating(false);
        notifySuccess('App created successfully');
        navigate('/apps');
      }
    } catch (error) {
      console.error('Error creating app:', error);
      setCreating(false);
    }
  };

  const handleCancel = () => {
    navigate('/apps');
  };

  const handleAddLocalApp = () => {
    form.setValue('app_name', 'localhost');
    form.setValue('public_url', 'http://localhost:8001');
    form.setValue('private_url', 'http://localhost:8001');
  };

  const handleRemoveLocalApp = () => {
    form.setValue('app_name', '');
    form.setValue('public_url', '');
    form.setValue('private_url', '');
  };

  return (
    <div className="flex h-full items-center justify-center bg-gray-50 bg-[url('/background.webp')] bg-cover bg-center p-6 px-[210px] pt-[139px] pb-[138px]">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(appCreationSubmit)}
          className="flex w-full max-w-[940px] flex-col gap-16 rounded-2xl bg-white p-8 shadow-[0_4px_40px_0_rgba(0,0,0,0.04)]"
        >
          <div className="flex justify-between">
            <div className="mb-2">
              <p className="text-2xl font-semibold text-black">Create new app</p>
              <p className="text-lg font-normal text-[#585858]">Add a new application to the console</p>
            </div>
            {appEnv.isLocal && (
              <label htmlFor="add-local-app" className="flex cursor-pointer items-center gap-2">
                <Checkbox
                  id="add-local-app"
                  onCheckedChange={(checked) => {
                    if (checked) handleAddLocalApp();
                    else handleRemoveLocalApp();
                  }}
                />
                <span className="text-sm font-normal text-[#585858]">Create local app for development</span>
              </label>
            )}
          </div>
          <div className="flex flex-col gap-10">
            <div className="flex justify-between gap-10">
              <FormField
                control={form.control}
                name="app_name"
                render={({ field }) => (
                  <FormItem className="flex w-full flex-col">
                    <FormLabel>App Name</FormLabel>
                    <FormControl>
                      <Input placeholder="My Application" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="deployment_type"
                render={({ field }) => (
                  <FormItem className="flex w-full cursor-pointer flex-col">
                    <FormLabel>Deployment Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="cursor-pointer">
                          <SelectValue placeholder="Select Deployment Type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem disabled={true} className="cursor-pointer" value="auto">
                          Auto
                        </SelectItem>
                        <SelectItem className="cursor-pointer" value="manual">
                          Manual
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="overflow-hidden transition-all duration-300 ease-in-out">
              <div className="grid w-full grid-cols-2 gap-10">
                <FormField
                  control={form.control}
                  name="public_url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Public URL</FormLabel>
                      <FormControl>
                        <Input placeholder="https://myapp.example.com" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="private_url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Private URL</FormLabel>
                      <FormControl>
                        <Input placeholder="http://36.77.240.111:8000" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-4">
            <Button variant="outline" type="button" onClick={handleCancel}>
              Cancel
            </Button>
            <Button type="submit" loading={creating}>
              Create App
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
};

export default CreateApp;
