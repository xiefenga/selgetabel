import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, Link } from "react-router";
import { Loader2, UserPlus, Mail, User, Lock } from "lucide-react";

import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Field, FieldContent, FieldError, FieldLabel } from "~/components/ui/field";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";

import { register as registerUser } from "~/api/auth";

import type { Route } from "./+types/_public.register";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "注册 - Selgetabel" },
    { name: "description", content: "注册 Selgetabel 账户" },
  ];
}

const RegisterPage = () => {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<{
    username: string;
    email: string;
    password: string;
    confirmPassword: string;
  }>({
    defaultValues: {
      username: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
    mode: "onChange",
  });
  const {
    handleSubmit,
    register,
    getValues,
    formState: { errors, isSubmitting, isValid },
  } = form;

  const handleRegister = async (values: {
    username: string;
    email: string;
    password: string;
    confirmPassword: string;
  }) => {
    setError(null);

    try {
      await registerUser({
        username: values.username,
        email: values.email,
        password: values.password,
      });
      // 注册成功，跳转到登录页
      navigate("/login", {
        replace: true,
        state: { message: "注册成功，请登录" }
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "注册失败，请重试";
      setError(errorMessage);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header - outside card for cleaner look */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-gray-900">创建账户</h1>
        <p className="text-gray-500">开始您的智能数据处理之旅</p>
      </div>

      <Card className="shadow-xl border border-gray-100 bg-white/80 backdrop-blur-sm">
        <CardHeader className="sr-only">
          <CardTitle>注册</CardTitle>
          <CardDescription>注册表单</CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit(handleRegister)} className="space-y-4">
            {/* Error Message */}
            {error && (
              <div className="bg-error/10 border border-error/30 text-error px-4 py-3 rounded-xl text-sm animate-in fade-in slide-in-from-top-2">
                {error}
              </div>
            )}

            {/* Username Input */}
            <Field data-invalid={Boolean(errors.username)}>
              <FieldLabel htmlFor="username" className="text-gray-700 flex items-center gap-2">
                <User className="w-4 h-4 text-gray-400" />
                用户名
              </FieldLabel>
              <FieldContent>
                <Input
                  id="username"
                  type="text"
                  placeholder="请输入用户名"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.username)}
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  {...register("username", {
                    required: "请输入用户名",
                    minLength: { value: 2, message: "用户名至少 2 位" },
                  })}
                />
                <FieldError errors={[errors.username]} className="text-xs text-error" />
              </FieldContent>
            </Field>

            {/* Email Input */}
            <Field data-invalid={Boolean(errors.email)}>
              <FieldLabel htmlFor="email" className="text-gray-700 flex items-center gap-2">
                <Mail className="w-4 h-4 text-gray-400" />
                邮箱
              </FieldLabel>
              <FieldContent>
                <Input
                  id="email"
                  type="email"
                  placeholder="请输入邮箱地址"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.email)}
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  {...register("email", {
                    required: "请输入邮箱",
                    pattern: {
                      value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                      message: "邮箱格式不正确",
                    },
                  })}
                />
                <FieldError errors={[errors.email]} className="text-xs text-error" />
              </FieldContent>
            </Field>

            {/* Password Row - Two columns on larger screens */}
            <div className="grid gap-4 sm:grid-cols-2">
              {/* Password Input */}
              <Field data-invalid={Boolean(errors.password)}>
                <FieldLabel htmlFor="password" className="text-gray-700 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-gray-400" />
                  密码
                </FieldLabel>
                <FieldContent>
                  <Input
                    id="password"
                    type="password"
                    placeholder="至少 6 位"
                    disabled={isSubmitting}
                    aria-invalid={Boolean(errors.password)}
                    className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                    {...register("password", {
                      required: "请输入密码",
                      minLength: { value: 6, message: "密码长度至少为 6 位" },
                    })}
                  />
                  <FieldError errors={[errors.password]} className="text-xs text-error" />
                </FieldContent>
              </Field>

              {/* Confirm Password Input */}
              <Field data-invalid={Boolean(errors.confirmPassword)}>
                <FieldLabel htmlFor="confirmPassword" className="text-gray-700 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-gray-400" />
                  确认密码
                </FieldLabel>
                <FieldContent>
                  <Input
                    id="confirmPassword"
                    type="password"
                    placeholder="再次输入"
                    disabled={isSubmitting}
                    aria-invalid={Boolean(errors.confirmPassword)}
                    className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                    {...register("confirmPassword", {
                      required: "请再次输入密码",
                      validate: (value) =>
                        value === getValues("password") || "两次输入的密码不一致",
                    })}
                  />
                  <FieldError errors={[errors.confirmPassword]} className="text-xs text-error" />
                </FieldContent>
              </Field>
            </div>

            {/* Terms */}
            {/* <p className="text-xs text-gray-400 leading-relaxed">
              注册即表示您同意我们的{" "}
              <button type="button" className="text-brand hover:underline">服务条款</button>
              {" "}和{" "}
              <button type="button" className="text-brand hover:underline">隐私政策</button>
            </p> */}

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={isSubmitting || !isValid}
              className="w-full h-12 bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-semibold text-base shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 transition-all duration-300 rounded-xl"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  注册中...
                </>
              ) : (
                <>
                  <UserPlus className="w-5 h-5 mr-2" />
                  创建账户
                </>
              )}
            </Button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-3 text-gray-400">或</span>
            </div>
          </div>

          {/* Footer */}
          <div className="text-center">
            <p className="text-sm text-gray-500">
              已有账户？{" "}
              <Link
                to="/login"
                className="text-brand hover:text-brand-dark font-semibold underline-offset-4 hover:underline transition-colors"
              >
                立即登录
              </Link>
            </p>
          </div>
        </CardContent>
      </Card>

    </div>
  );
};

export default RegisterPage;
