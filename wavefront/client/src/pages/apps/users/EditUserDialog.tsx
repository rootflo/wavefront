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
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { IUser, UpdateUserInput, updateUserSchema } from '@app/types/user';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';

interface EditUserDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  user: IUser;
  onSuccess?: () => void;
}

const EditUserDialog: React.FC<EditUserDialogProps> = ({ isOpen, onOpenChange, user, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const form = useForm<UpdateUserInput>({
    resolver: zodResolver(updateUserSchema),
    defaultValues: {
      password: '',
      first_name: user.first_name,
      last_name: user.last_name,
    },
  });

  // Reset form when user changes
  useEffect(() => {
    if (isOpen && user) {
      form.reset({
        password: '',
        first_name: user.first_name,
        last_name: user.last_name,
      });
    }
  }, [isOpen, user, form]);

  const onSubmit = async (data: UpdateUserInput) => {
    try {
      // Filter out empty values
      const updateData: {
        password?: string;
        first_name?: string;
        last_name?: string;
      } = {};

      if (data.password && data.password.trim()) {
        updateData.password = data.password;
      }
      if (data.first_name && data.first_name !== user.first_name) {
        updateData.first_name = data.first_name;
      }
      if (data.last_name && data.last_name !== user.last_name) {
        updateData.last_name = data.last_name;
      }

      if (Object.keys(updateData).length === 0) {
        notifyError('No changes to update');
        return;
      }

      await floConsoleService.userService.updateUser(user.id, updateData);
      notifySuccess('User updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update user');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit User</DialogTitle>
          <DialogDescription>Update user information</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Password (Optional)</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="Leave empty to keep current password" {...field} />
                  </FormControl>
                  <FormDescription>Only fill this if you want to change the password</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="first_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>First Name</FormLabel>
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
                  <FormLabel>Last Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Doe" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Update User
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditUserDialog;
