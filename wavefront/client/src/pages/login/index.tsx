import floConsoleService from "@app/api";
import { RootfloIcon } from "@app/assets/icons";
import aiCircle from "@app/assets/images/ai_circle.png";
import { Button } from "@app/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@app/components/ui/form";
import { Input } from "@app/components/ui/input";
import { TOKEN_KEY } from "@app/lib/constants";
import { useAuthStore, useNotifyStore } from "@app/store";
import { validationMessage } from "@app/utils/form-validation";
import { emailRegex } from "@app/utils/regex";
import { zodResolver } from "@hookform/resolvers/zod";
import { EyeIcon, EyeOffIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

export const LoginSchema = z.object({
  email: z
    .string({
      required_error: validationMessage.isRequired("Email"),
    })
    .regex(emailRegex, { message: validationMessage.isInvalid("Email") }),
  password: z
    .string({
      required_error: validationMessage.isRequired("Password"),
    })
    .min(8, { message: validationMessage.minValue("Password", 8) }),
});

const Login = () => {
  const { setAuthenticatedState } = useAuthStore();
  const { notifyError } = useNotifyStore();
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);

  const form = useForm<z.infer<typeof LoginSchema>>({
    resolver: zodResolver(LoginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const handleLogin = async (value: z.infer<typeof LoginSchema>) => {
    try {
      setIsLoading(true);
      const { data } = await floConsoleService.consoleAuthService.authenticate(
        value
      );
      localStorage.setItem(TOKEN_KEY, data?.data?.user.access_token || "");
      setAuthenticatedState(true);
      navigate("/apps");
    } catch (err) {
      notifyError("Email or password incorrect. \nPlease try again");
      console.log(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      setAuthenticatedState(true);
      navigate("/apps");
    }
  }, []);

  return (
    <div
      id="login__page"
      className="flex h-full w-full flex-col items-center justify-center gap-12"
    >
      <div className="flex h-[100px] w-[100px] animate-[spin_3s_linear_infinite] items-center justify-center rounded-[50%]">
        <img src={aiCircle} alt="" className="rounded-full" />
      </div>
      <div className="flex w-full max-w-[320px] flex-col items-center justify-center gap-8 rounded-2xl bg-white p-8 shadow-[0px_0px_32px_0px_rgba(0,0,0,0.06)] sm:max-w-[480px]">
        <RootfloIcon />
        <div className="flex w-full flex-col items-center justify-center">
          <p className="text-2xl font-medium text-black">Welcome back!</p>
          <p className="text-gray_text text-base font-normal">
            Enter your credentials to access your account
          </p>
        </div>
        <Form {...form}>
          <form
            className="flex w-full flex-col gap-6"
            onSubmit={form.handleSubmit(handleLogin)}
          >
            <div className="flex w-full flex-col gap-3">
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <div className="border-border_color focus-within:ring-border_color flex h-12 items-center gap-3 rounded-lg border px-3 py-2 focus-within:ring-1">
                        {/* <EmailIcon /> */}
                        <Input
                          type="email"
                          placeholder="Enter email"
                          autoComplete="off"
                          className="text-gray_text w-full border-0 bg-transparent text-base font-medium shadow-none outline-none focus-visible:ring-0"
                          {...field}
                        />
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <div className="border-border_color focus-within:ring-border_color flex h-12 items-center gap-3 rounded-lg border px-3 py-2 focus-within:ring-1">
                        {/* <PasswordIcon /> */}
                        <Input
                          type={showPassword ? "text" : "password"}
                          placeholder="Enter password"
                          autoComplete="off"
                          className="text-gray_text w-full border-0 bg-transparent text-base font-medium shadow-none outline-none focus-visible:ring-0"
                          {...field}
                        />
                        <div
                          className="cursor-pointer"
                          onClick={() => setShowPassword(!showPassword)}
                        >
                          {showPassword ? (
                            <EyeIcon className="size-4" />
                          ) : (
                            <EyeOffIcon className="size-4" />
                          )}
                        </div>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <Button type="submit" loading={isLoading} disabled={isLoading}>
              Sign in
            </Button>
          </form>
        </Form>
      </div>
      <div className="flex gap-2 text-base">
        <p className="text-gray_text font-normal">Forgot your password?</p>
        <Link to="/forgot-password" className="text-heading font-medium">
          Reset here
        </Link>
      </div>
    </div>
  );
};

export default Login;
