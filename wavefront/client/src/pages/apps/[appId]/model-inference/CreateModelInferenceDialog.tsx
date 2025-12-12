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
import { useDashboardStore, useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const createModelInferenceSchema = z.object({
  modelType: z.string().min(1, 'Model type is required'),
  modelFile: z.custom<File>((val) => val instanceof File, { message: 'Model file is required' }),
});

type CreateModelInferenceInput = z.infer<typeof createModelInferenceSchema>;

interface CreateModelInferenceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateModelInferenceDialog: React.FC<CreateModelInferenceDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [creating, setCreating] = useState(false);
  const { selectedApp } = useDashboardStore();
  const form = useForm<CreateModelInferenceInput>({
    resolver: zodResolver(createModelInferenceSchema),
    defaultValues: {
      modelType: '',
      modelFile: undefined as any,
    },
    mode: 'onChange',
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        modelType: '',
        modelFile: undefined as any,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateModelInferenceInput) => {
    setCreating(true);
    try {
      const response = await floConsoleService.modelInferenceService.uploadModel(data.modelType, data.modelFile);

      if (response.data && response.data.data) {
        notifySuccess(`Model '${response.data.data.model_id}' created successfully`);

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        // Optionally navigate to the created model if we have the ID
        if (response.data.data.model_id) {
          navigate(`/apps/${appId}/model-inference/${response.data.data.model_id}`);
        }
      } else {
        notifyError('Failed to get model ID after upload.');
      }
    } catch (error: any) {
      console.error('Error creating model:', error);
      const errorMessage = error?.message || 'Failed to create model';
      notifyError(errorMessage);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Upload New Model</DialogTitle>
          <DialogDescription>Upload a new model for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="modelType"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Model Type<span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., image-classification" {...field} />
                  </FormControl>
                  <FormDescription>
                    Categorization of the model (e.g., 'image-classification', 'object-detection')
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="modelFile"
              render={({ field: { value, onChange, ...field } }) => (
                <FormItem>
                  <FormLabel>
                    Model File<span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="file"
                      {...field}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          onChange(file);
                        }
                      }}
                      className="w-full cursor-pointer rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-black outline-none file:cursor-pointer file:text-blue-500"
                    />
                  </FormControl>
                  {value && (
                    <FormDescription className="text-sm text-gray-600">
                      Selected file: {(value as File).name}
                    </FormDescription>
                  )}
                  <FormDescription>The model file to be uploaded</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={creating || form.formState.isSubmitting}>
                Upload Model
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateModelInferenceDialog;
