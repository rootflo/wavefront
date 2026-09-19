import floService from '@app/api';
import ThemeToggle from '@app/components/ThemeToggle';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { z } from 'zod';

export const ResetPasswordSchema = z.object({
  password: z
    .string()
    .min(8)
    .regex(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/, {
      message:
        'Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.',
    }),
  confirmPassword: z
    .string()
    .min(8)
    .regex(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/, {
      message:
        'Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.',
    }),
});

const ResetPasswordPage = () => {
  const { notifyError, notifySuccess } = useNotifyStore();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();

  const form = useForm<z.infer<typeof ResetPasswordSchema>>({
    resolver: zodResolver(ResetPasswordSchema),
  });

  const handleResetSubmit = async (values: z.infer<typeof ResetPasswordSchema>) => {
    if (!token) {
      notifyError('Invalid password reset link');
      return;
    }

    try {
      const resetUser = await floService.userService.resetPassword(token, values.password);
      if (resetUser.status === 200) {
        notifySuccess('Your password has been updated successfully');
        navigate('/login');
      }
    } catch (err) {
      console.log('in error', err);
    }
  };

  return (
    <div className="relative flex h-full w-full flex-col items-center justify-center gap-8">
      <div className="absolute top-5 right-5">
        <ThemeToggle />
      </div>
      <div className="frost-card ring-frost-border flex w-full max-w-[320px] flex-col items-center justify-center gap-8 rounded-2xl border p-8 ring-1 sm:max-w-[480px]">
        <div className="flex w-full flex-col items-center justify-center">
          <p className="frost-text text-2xl font-medium">Only one step left</p>
          <p className="frost-text-muted text-base font-normal">Enter your new password</p>
        </div>

        <Form {...form}>
          <form className="flex w-full flex-col gap-4" onSubmit={form.handleSubmit(handleResetSubmit)}>
            <div className="flex w-full flex-col gap-5">
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Password</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="New password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Confirm Password</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="Confirm password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <Button type="submit" className="h-12 w-full">
              Submit
            </Button>
          </form>
        </Form>
      </div>
      <Link to="/login" className="text-brand text-sm font-medium hover:underline">
        Back to login
      </Link>
    </div>
  );
};
export default ResetPasswordPage;
