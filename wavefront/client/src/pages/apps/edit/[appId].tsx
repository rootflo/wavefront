import AppsBackdrop from '@app/components/AppsBackdrop';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetAppById, useUpdateApp } from '@app/hooks';
import { zodResolver } from '@hookform/resolvers/zod';
import { X } from 'lucide-react';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';
import { createAppSchema } from '../schemas';

type TEditAppInputSchema = z.infer<typeof createAppSchema>;

const EditApp: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();

  const { data: response } = useGetAppById(appId!, !!appId);
  const { mutate: updateApp, isPending: isUpdating } = useUpdateApp();
  // Extract app data from response - adjust based on actual API response structure
  const appData = response;

  const form = useForm<TEditAppInputSchema>({
    resolver: zodResolver(createAppSchema),
    defaultValues: {
      deployment_type: 'auto' as 'manual' | 'auto',
      app_name: '',
      public_url: '',
      private_url: '',
    },
  });

  // Reset form with app data when it's loaded
  useEffect(() => {
    if (appData) {
      form.reset({
        deployment_type: (appData.deployment_type as 'manual' | 'auto') || 'auto',
        app_name: appData.app_name || '',
        public_url: appData.public_url || '',
        private_url: appData.private_url || '',
      });
    }
  }, [appData, form]);

  const handleEditAppSubmit = (formData: TEditAppInputSchema) => {
    updateApp(
      {
        appId: appId!,
        data: {
          app_name: formData.app_name,
          public_url: formData.public_url!,
          private_url: formData.private_url!,
        },
      },
      { onSuccess: () => navigate('/apps') }
    );
  };

  const handleCancel = () => {
    navigate('/apps');
  };

  return (
    <div className="frost-canvas relative isolate flex h-full items-start justify-center overflow-y-auto p-4 sm:p-6 md:items-center md:px-[210px] md:pt-[139px] md:pb-[138px]">
      <AppsBackdrop />
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(handleEditAppSubmit)}
          className="frost-card ring-frost-border relative flex w-full max-w-[940px] flex-col gap-8 rounded-2xl border p-4 ring-1 sm:gap-16 sm:p-8"
        >
          <div className="flex justify-between">
            <div className="flex flex-col gap-2">
              <p className="frost-text text-2xl font-semibold">Edit app</p>
              <p className="frost-text-muted text-lg font-normal">Update application configuration</p>
            </div>
            <button
              type="button"
              className="frost-text-muted hover:text-frost-text cursor-pointer"
              onClick={handleCancel}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-col gap-10">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:gap-10">
              <FormField
                control={form.control}
                name="app_name"
                render={({ field }) => (
                  <FormItem className="flex w-full flex-col">
                    <FormLabel className="frost-text">App Name</FormLabel>
                    <FormControl>
                      <Input placeholder="My Application" disabled {...field} />
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
                    <FormLabel className="frost-text">Deployment Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value} disabled>
                      <FormControl>
                        <SelectTrigger className="cursor-pointer">
                          <SelectValue placeholder="Select Deployment Type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem className="cursor-pointer" value="auto">
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

            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:gap-10">
              <FormField
                control={form.control}
                name="public_url"
                render={({ field }) => (
                  <FormItem className="flex w-full flex-col">
                    <FormLabel className="frost-text">Public URL</FormLabel>
                    <FormControl>
                      <Input placeholder="https://myapp.example.com" {...field} autoFocus />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="private_url"
                render={({ field }) => (
                  <FormItem className="flex w-full flex-col">
                    <FormLabel className="frost-text">Private URL</FormLabel>
                    <FormControl>
                      <Input placeholder="https://myapp.example.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </div>
          <div className="flex justify-end gap-4">
            <Button variant="outline" type="button" onClick={handleCancel}>
              Cancel
            </Button>
            <Button type="submit" loading={isUpdating}>
              Update App
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
};

export default EditApp;
