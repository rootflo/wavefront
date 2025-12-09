import floConsoleService from "@app/api";
import { Button } from "@app/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@app/components/ui/form";
import { Input } from "@app/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@app/components/ui/select";
import { useNotifyStore } from "@app/store";
import { CreateAppRequest } from "@app/types/app";
import { zodResolver } from "@hookform/resolvers/zod";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";
import { createAppSchema } from "./schemas";

type TCreateAppInputSchema = z.infer<typeof createAppSchema>;

const CreateApp: React.FC = () => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [creating, setCreating] = useState(false);
  const [pollingAppId, setPollingAppId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );

  const form = useForm<TCreateAppInputSchema>({
    resolver: zodResolver(createAppSchema),
    defaultValues: {
      deployment_type: "auto",
    },
  });

  const deploymentType = form.watch("deployment_type");

  // Polling function to check app status
  const pollAppStatus = useCallback(
    async (appId: string) => {
      try {
        const { data } = await floConsoleService.appService.getAppStatus(appId);
        if (data.data?.status === "success") {
          // Clear polling interval
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setPollingAppId(null);
          setCreating(false);
          notifySuccess("App created successfully");
          navigate("/apps");
        }
      } catch (error) {
        console.error("Error polling app status:", error);
        // Stop polling on error
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setPollingAppId(null);
        setCreating(false);
        notifyError("Failed to check app status");
      }
    },
    [notifySuccess, notifyError, navigate]
  );

  // Effect to handle polling
  useEffect(() => {
    if (pollingAppId) {
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
  }, [pollingAppId, pollAppStatus]);

  const appCreationSubmit = async (formData: TCreateAppInputSchema) => {
    setCreating(true);
    try {
      // Transform form data to match CreateAppRequest type
      const appData: CreateAppRequest = {
        app_name: formData.app_name,
        deployment_type: formData.deployment_type,
        app_url: formData.app_url || "",
        app_secret: formData.app_secret || "",
        app_key: formData.app_key || "",
      };

      const response = await floConsoleService.appService.createApp(appData);

      if (response.data?.data?.app.status === "in_progress") {
        // Start polling for status updates
        setPollingAppId(response.data.data.app.id);
      } else if (response.data?.data?.app.status === "success") {
        // If already successful, show success immediately
        setCreating(false);
        notifySuccess("App created successfully");
        navigate("/apps");
      }
    } catch (error) {
      console.error("Error creating app:", error);
      notifyError("Failed to create app");
      setCreating(false);
    }
  };

  const handleCancel = () => {
    navigate("/apps");
  };

  return (
    <div className="flex h-full items-center justify-center bg-gray-50 bg-[url('/background.webp')] bg-cover bg-center p-6 px-[210px] pb-[138px] pt-[139px]">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(appCreationSubmit)}
          className="flex w-full max-w-[940px] flex-col gap-16 rounded-2xl bg-white p-8 shadow-[0_4px_40px_0_rgba(0,0,0,0.04)]"
        >
          <div className="flex flex-col gap-2">
            <p className="text-2xl font-semibold text-black">Create new app</p>
            <p className="text-lg font-normal text-[#585858]">
              Add a new application to the console
            </p>
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

            <div
              className={`overflow-hidden transition-all duration-300 ease-in-out ${
                deploymentType === "manual"
                  ? "max-h-[500px] opacity-100"
                  : "max-h-0 opacity-0"
              }`}
            >
              <div className="flex w-full flex-col gap-4">
                <div className="grid w-full grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="app_url"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>App URL</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="https://myapp.example.com"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="app_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>App Key</FormLabel>
                        <FormControl>
                          <Input placeholder="Enter App Key" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
                <FormField
                  control={form.control}
                  name="app_secret"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>App Secret</FormLabel>
                      <FormControl>
                        <Input placeholder="Enter App Secret" {...field} />
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
