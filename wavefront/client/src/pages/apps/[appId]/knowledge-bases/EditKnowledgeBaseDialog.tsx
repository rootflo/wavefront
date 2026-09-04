import floConsoleService from '@app/api';
import { KbData, UpdateKnowledgeBasePayload } from '@app/api/knowledge-base-service';
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
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const editKnowledgeBaseSchema = z.object({
  name: z.string().min(1, 'Knowledge base name is required'),
  type: z.string().min(1, 'Type is required'),
  description: z.string().optional(),
});

type EditKnowledgeBaseInput = z.infer<typeof editKnowledgeBaseSchema>;

interface EditKnowledgeBaseDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeBase: KbData;
  onSuccess?: () => void;
}

const EditKnowledgeBaseDialog: React.FC<EditKnowledgeBaseDialogProps> = ({
  isOpen,
  onOpenChange,
  knowledgeBase,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const form = useForm<EditKnowledgeBaseInput>({
    resolver: zodResolver(editKnowledgeBaseSchema),
    defaultValues: {
      name: '',
      type: '',
      description: '',
    },
  });

  useEffect(() => {
    if (knowledgeBase && isOpen) {
      form.reset({
        name: knowledgeBase.name || '',
        type: knowledgeBase.type || '',
        description: knowledgeBase.description || '',
      });
    }
  }, [knowledgeBase, isOpen, form]);

  const onSubmit = async (data: EditKnowledgeBaseInput) => {
    try {
      const payload: UpdateKnowledgeBasePayload = {
        name: data.name.trim(),
        description: data.description?.trim() || '',
        type: data.type.trim(),
      };

      await floConsoleService.knowledgeBaseService.updateKnowledgeBase(knowledgeBase.id, payload);

      notifySuccess(`Knowledge Base '${payload.name}' updated successfully`);
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      console.error('Error updating knowledge base:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update knowledge base');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Edit Knowledge Base</DialogTitle>
          <DialogDescription>Update the details for this knowledge base</DialogDescription>
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

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditKnowledgeBaseDialog;
