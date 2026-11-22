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
import { useCreateUser, useUpdateUser } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { CreateUserInput, IUser, createUserSchema, updateUserSchema } from '@app/types/user';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect } from 'react';
import { Resolver, useForm } from 'react-hook-form';

const toFormValues = (user?: IUser): CreateUserInput => ({
  email: user?.email ?? '',
  password: '',
  first_name: user?.first_name ?? '',
  last_name: user?.last_name ?? '',
  role: 'app_admin',
});

const Required = () => <span className="text-red-500">*</span>;

interface UserFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** The user to edit; omit to create one. Render separate instances for create and edit. */
  user?: IUser;
}

const UserFormDialog: React.FC<UserFormDialogProps> = ({ isOpen, onOpenChange, user }) => {
  const { notifyError } = useNotifyStore();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const isEdit = !!user;
  const saving = createUser.isPending || updateUser.isPending;

  // Editing has no email or role field and leaves every field optional
  const form = useForm<CreateUserInput>({
    resolver: zodResolver(isEdit ? updateUserSchema : createUserSchema) as unknown as Resolver<CreateUserInput>,
    defaultValues: toFormValues(user),
  });

  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(user));
    }
  }, [isOpen, user, form]);

  const close = () => onOpenChange(false);

  const onSubmit = (data: CreateUserInput) => {
    if (!user) {
      createUser.mutate(data, { onSuccess: close });
      return;
    }

    // Send only what changed
    const updateData: { password?: string; first_name?: string; last_name?: string } = {};
    if (data.password?.trim()) updateData.password = data.password;
    if (data.first_name && data.first_name !== user.first_name) updateData.first_name = data.first_name;
    if (data.last_name && data.last_name !== user.last_name) updateData.last_name = data.last_name;

    if (Object.keys(updateData).length === 0) {
      notifyError('No changes to update');
      return;
    }
    updateUser.mutate({ userId: user.id, data: updateData }, { onSuccess: close });
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit User' : 'Create New User'}</DialogTitle>
          <DialogDescription>{isEdit ? 'Update user information' : 'Add a new user to the system'}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {!isEdit && (
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Email <Required />
                    </FormLabel>
                    <FormControl>
                      <Input type="email" placeholder="user@example.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {isEdit ? (
                      'Password (Optional)'
                    ) : (
                      <>
                        Password <Required />
                      </>
                    )}
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      placeholder={isEdit ? 'Leave empty to keep current password' : 'Enter password'}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="first_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>First Name {!isEdit && <Required />}</FormLabel>
                  <FormControl>
                    <Input placeholder="John" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="last_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Last Name {!isEdit && <Required />}</FormLabel>
                  <FormControl>
                    <Input placeholder="Doe" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {!isEdit && (
              <FormField
                control={form.control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a role" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="app_admin">App Admin</SelectItem>
                        <SelectItem value="owner">Owner</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {isEdit ? 'Update User' : 'Create User'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default UserFormDialog;
