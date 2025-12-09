import floService from "@app/api";
import { Button } from "@app/components/ui/button";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@app/components/ui/form";
import { Input } from "@app/components/ui/input";
import { useNotifyStore } from "@app/store";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

export const ResetPasswordSchema = z.object({
  password: z
    .string()
    .min(8)
    .regex(
      /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/,
      {
        message:
          "Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.",
      }
    ),
  confirmPassword: z
    .string()
    .min(8)
    .regex(
      /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/,
      {
        message:
          "Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.",
      }
    ),
});

const ResetPasswordPage = () => {
  const { notifyError, notifySuccess } = useNotifyStore();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const navigate = useNavigate();

  const form = useForm<z.infer<typeof ResetPasswordSchema>>({
    resolver: zodResolver(ResetPasswordSchema),
  });

  const handleResetSubmit = async (
    values: z.infer<typeof ResetPasswordSchema>
  ) => {
    if (!token) {
      notifyError("Invalid password reset link");
      return;
    }

    try {
      const resetUser = await floService.userService.resetPassword(
        token,
        values.password
      );
      if (resetUser.status === 200) {
        notifySuccess("Your password has been updated successfully");
        navigate("/login");
      }
    } catch (err) {
      console.log("in error", err);
    }
  };

  return (
    <div className="flex w-full max-w-[320px] flex-col items-center justify-center gap-8 rounded-2xl bg-white p-8 shadow-[0px_0px_32px_0px_rgba(0,0,0,0.06)] sm:max-w-[480px]">
      <div className="flex w-full flex-col items-center justify-center">
        <p className="text-2xl font-medium text-black">Only one step left</p>
        <p className="text-gray_text text-base font-normal">
          Enter your new password
        </p>
      </div>

      <form
        className="flex w-full flex-col gap-4"
        onSubmit={form.handleSubmit(handleResetSubmit)}
      >
        <div className="flex w-full flex-col gap-5">
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="New password"
                    {...field}
                  />
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
                <FormLabel>Confirm Password</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="Confirm password"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <Button
          type="submit"
          className="bg-heading flex h-12 w-full items-center justify-center gap-2.5 rounded-xl text-base font-semibold text-white"
        >
          Submit
        </Button>
      </form>
    </div>
  );
};
export default ResetPasswordPage;
