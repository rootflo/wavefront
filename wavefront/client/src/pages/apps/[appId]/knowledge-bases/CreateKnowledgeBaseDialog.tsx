import floConsoleService from '@app/api';
import { NewKnowledgeBasePayload } from '@app/api/knowledge-base-service';
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
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const createKnowledgeBaseSchema = z.object({
  name: z.string().min(1, 'Knowledge base name is required'),
  type: z.string().min(1, 'Type is required'),
  description: z.string().optional(),
  vector_size: z.number().min(1, 'Vector size must be at least 1'),
});

type CreateKnowledgeBaseInput = z.infer<typeof createKnowledgeBaseSchema>;

interface CreateKnowledgeBaseDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateKnowledgeBaseDialog: React.FC<CreateKnowledgeBaseDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const form = useForm<CreateKnowledgeBaseInput>({
    resolver: zodResolver(createKnowledgeBaseSchema),
    defaultValues: {
      name: '',
      type: '',
      description: '',
      vector_size: 1536,
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        name: '',
        type: '',
        description: '',
        vector_size: 1536,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateKnowledgeBaseInput) => {
    if (!appId) {
      notifyError('Knowledge base service not available');
      return;
    }

    try {
      const payload: NewKnowledgeBasePayload = {
        name: data.name.trim(),
        description: data.description?.trim() || '',
        type: data.type.trim(),
        vector_size: data.vector_size,
      };

      const response = await floConsoleService.knowledgeBaseService.createKnowledgeBase(payload);

      if (response.data?.data) {
        notifySuccess(`Knowledge Base '${response.data.data.data.name}' created successfully`);

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        // Navigate to the created knowledge base
        if (response.data.data.data.id) {
          navigate(`/apps/${appId}/knowledge-bases/${response.data.data.data.id}`);
        }
      } else {
        notifyError('Failed to get knowledge base ID after creation.');
      }
    } catch (error) {
      console.error('Error creating knowledge base:', error);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Knowledge Base</DialogTitle>
          <DialogDescription>Create a new knowledge base for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Knowledge Base Name<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Customer Support FAQ" {...field} />
                    </FormControl>
                    <FormDescription>A unique name for your knowledge base</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Type<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., General" {...field} />
                    </FormControl>
                    <FormDescription>The type of your knowledge base</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <textarea
                      rows={3}
                      placeholder="A brief description of the knowledge base's purpose"
                      className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex min-h-[80px] w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>Provide a description for your knowledge base</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="vector_size"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Vector Size<span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="e.g., 1536"
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormDescription>The vector size for your knowledge base</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Create Knowledge Base
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateKnowledgeBaseDialog;
