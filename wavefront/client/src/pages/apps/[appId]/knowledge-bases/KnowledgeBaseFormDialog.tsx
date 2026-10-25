import { KbData, KNOWLEDGE_BASE_TYPES } from '@app/api/knowledge-base-service';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useCreateKnowledgeBase, useUpdateKnowledgeBase } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const knowledgeBaseSchema = z.object({
  name: z.string().min(1, 'Knowledge base name is required'),
  type: z.enum(['text', 'image'], { message: 'Type is required' }),
  description: z.string().optional(),
});

type KnowledgeBaseInput = z.infer<typeof knowledgeBaseSchema>;

const toFormValues = (knowledgeBase?: KbData): KnowledgeBaseInput => ({
  name: knowledgeBase?.name || '',
  type: knowledgeBase?.type ?? 'text',
  description: knowledgeBase?.description || '',
});

const typeLabel = (type: string) => KNOWLEDGE_BASE_TYPES.find((t) => t.value === type)?.label ?? type;

interface KnowledgeBaseFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  /** The knowledge base to edit; omit to create one. */
  knowledgeBase?: KbData;
}

const KnowledgeBaseFormDialog: React.FC<KnowledgeBaseFormDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  knowledgeBase,
}) => {
  const { selectedApp } = useDashboardStore();
  const createKnowledgeBase = useCreateKnowledgeBase(appId);
  const updateKnowledgeBase = useUpdateKnowledgeBase(appId);
  const isEdit = !!knowledgeBase;
  const saving = createKnowledgeBase.isPending || updateKnowledgeBase.isPending;

  const form = useForm<KnowledgeBaseInput>({
    resolver: zodResolver(knowledgeBaseSchema),
    defaultValues: toFormValues(knowledgeBase),
  });

  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(knowledgeBase));
    }
  }, [knowledgeBase, isOpen, form]);

  const close = () => onOpenChange(false);

  const onSubmit = (data: KnowledgeBaseInput) => {
    const name = data.name.trim();
    const description = data.description?.trim() || '';
    if (knowledgeBase) {
      updateKnowledgeBase.mutate({ kbId: knowledgeBase.id, payload: { name, description } }, { onSuccess: close });
    } else {
      createKnowledgeBase.mutate({ name, description, type: data.type }, { onSuccess: close });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Knowledge Base' : 'Create New Knowledge Base'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update the details for this knowledge base'
              : `Create a new knowledge base for ${selectedApp?.app_name ?? ''}`}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
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
                    <FormMessage />
                  </FormItem>
                )}
              />

              {isEdit ? (
                // The type decides the embedding models, so it is fixed at creation
                <FormItem>
                  <FormLabel>Type</FormLabel>
                  <Input disabled value={typeLabel(knowledgeBase.type)} />
                </FormItem>
              ) : (
                <FormField
                  control={form.control}
                  name="type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Type<span className="text-red-500">*</span>
                      </FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger className="cursor-pointer">
                            <SelectValue placeholder="Select a type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {KNOWLEDGE_BASE_TYPES.map((kbType) => (
                            <SelectItem key={kbType.value} className="cursor-pointer" value={kbType.value}>
                              {kbType.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-muted-foreground text-xs">
                        Accepts {KNOWLEDGE_BASE_TYPES.find((t) => t.value === field.value)?.accepts ?? '—'}. The type
                        can&apos;t be changed later.
                      </p>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
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
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {isEdit ? 'Save Changes' : 'Create Knowledge Base'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default KnowledgeBaseFormDialog;
