import floService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { cn } from '@app/lib/utils';
import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
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
    <div className="flex w-full max-w-[320px] flex-col items-center justify-center gap-8 rounded-2xl bg-white p-8 shadow-[0px_0px_32px_0px_rgba(0,0,0,0.06)] sm:max-w-[480px]">
      <div className="flex w-full flex-col items-center justify-center">
        <p className="text-2xl font-medium text-black">Only one step left</p>
        <p className="text-gray_text text-base font-normal">Enter your new email</p>
      </div>
      <Form {...form}>
        <form className="flex w-full flex-col gap-4" onSubmit={form.handleSubmit(submitEmail)}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input type="email" placeholder="Enter your email" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <p className={cn('text-sm text-red-500', message ? 'visible' : 'invisible')}>{message}</p>
          <Button
            type="submit"
            className="bg-heading flex h-12 w-full items-center justify-center gap-2.5 rounded-xl text-base font-semibold text-white"
          >
            Submit
          </Button>
        </form>
      </Form>
    </div>
  );
};

export default ForgotPasswordPage;
