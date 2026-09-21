import floService from '@app/api';
import ThemeToggle from '@app/components/ThemeToggle';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { cn } from '@app/lib/utils';
import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router';
import { z } from 'zod';

export const ForgotPasswordSchema = z.object({
  email: z.string().email(),
});

const ForgotPasswordPage = () => {
  const [message, setMessage] = useState('');

  const form = useForm<z.infer<typeof ForgotPasswordSchema>>({
    resolver: zodResolver(ForgotPasswordSchema),
  });

  const submitEmail = async (values: z.infer<typeof ForgotPasswordSchema>) => {
    try {
      const { data } = await floService.userService.resetPasswordEmailSend(values.email);
      setMessage(data.data.message);
    } catch (error) {
      console.error(error);
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
          <p className="frost-text-muted text-base font-normal">Enter your email</p>
        </div>
        <Form {...form}>
          <form className="flex w-full flex-col gap-4" onSubmit={form.handleSubmit(submitEmail)}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="frost-text">Email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="Enter your email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <p className={cn('text-sm text-red-500', message ? 'visible' : 'invisible')}>{message}</p>
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

export default ForgotPasswordPage;
