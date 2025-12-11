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
import { useGetAppById, useUpdateApp } from "@app/hooks";
import { useNotifyStore } from "@app/store";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import React, { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router";
import { z } from "zod";
import { createAppSchema } from "../schemas";

type TEditAppInputSchema = z.infer<typeof createAppSchema>;

const EditApp: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const { data: response } = useGetAppById(appId!, !!appId);
  const queryClient = useQueryClient();
  const { mutate: updateApp, isPending: isUpdating } = useUpdateApp(
    queryClient,
    notifySuccess,
    notifyError
  );
  // Extract app data from response - adjust based on actual API response structure
  const appData =
    (response as any)?.data?.data?.app ||
    (response as any)?.data?.app ||
    response;

  const form = useForm<TEditAppInputSchema>({
    resolver: zodResolver(createAppSchema),
    defaultValues: {
      deployment_type: "auto" as "manual" | "auto",
      app_name: "",
      public_url: "",
      private_url: "",
    },
  });

  // Reset form with app data when it's loaded
  useEffect(() => {
    if (appData) {
      form.reset({
        deployment_type:
          (appData.deployment_type as "manual" | "auto") || "auto",
        app_name: appData.app_name || "",
        public_url: appData.public_url || "",
        private_url: appData.private_url || "",
      });
    }
  }, [appData, form]);

  const handleEditAppSubmit = async (formData: TEditAppInputSchema) => {
    try {
      updateApp({
        appId: appId!,
        appName: formData.app_name,
        public_url: formData.public_url!,
        private_url: formData.private_url!,
      });
      navigate(`/apps`);
    } catch (error) {
      console.error("Error updating app:", error);
    }
  };

  const handleCancel = () => {
    navigate("/apps");
  };

  return (
    <div className="flex h-full items-center justify-center bg-gray-50 bg-[url('/background.webp')] bg-cover bg-center p-6 px-[210px] pb-[138px] pt-[139px]">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(handleEditAppSubmit)}
          className="flex w-full max-w-[940px] flex-col gap-16 rounded-2xl bg-white p-8 shadow-[0_4px_40px_0_rgba(0,0,0,0.04)]"
        >
          <div className="flex justify-between">
            <div className="flex flex-col gap-2">
              <p className="text-2xl font-semibold text-black">Edit app</p>
              <p className="text-lg font-normal text-[#585858]">
                Update application configuration
              </p>
            </div>
            <div className="cursor-pointer" onClick={handleCancel}>
              <X className="h-4 w-4" />
            </div>
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
                    <FormLabel>Deployment Type</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value}
                      disabled
                    >
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

            <div className="flex justify-between gap-10">
              <FormField
                control={form.control}
                name="public_url"
                render={({ field }) => (
                  <FormItem className="flex w-full flex-col">
                    <FormLabel>Public URL</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="https://myapp.example.com"
                        {...field}
                        autoFocus
                      />
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
                    <FormLabel>Private URL</FormLabel>
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
