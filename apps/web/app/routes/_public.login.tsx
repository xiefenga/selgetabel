import { useForm } from "react-hook-form";
import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, LogIn, CheckCircle2 } from "lucide-react";
import { useNavigate, Link, useLocation } from "react-router";

import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Field, FieldContent, FieldError, FieldLabel } from "~/components/ui/field";

import { login } from "~/api/auth";
import { useAuthStore } from "~/stores/auth";

import type { Route } from "./+types/_public.login";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "登录 - Selgetabel" },
    { name: "description", content: "登录到 Selgetabel 系统" },
  ];
}

const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const setUser = useAuthStore(state => state.setUser);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const {
    handleSubmit,
    register,
    formState: { errors, isSubmitting, isValid },
  } = useForm<{ account: string; password: string }>({
    defaultValues: { account: "", password: "" },
    mode: "onChange",
  });


  // 检查是否有注册成功的消息
  useEffect(() => {
    const state = location.state as { message?: string } | null;
    if (state?.message) {
      setSuccessMessage(state.message);
      // 清除 location state，避免刷新后仍显示
      window.history.replaceState({}, document.title);
    }
  }, [location]);

  const onLogin = async (values: { account: string; password: string }) => {
    setError(null);
    try {
      const userInfo = await login(values);
      // 更新 store 中的用户信息
      setUser(userInfo);
      // 使 react-query 缓存失效，触发重新获取
      await queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      // 登录成功，跳转到首页
      navigate("/");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "登录失败，请重试";
      setError(errorMessage);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header - outside card for cleaner look */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-gray-900">欢迎回来</h1>
        <p className="text-gray-500">登录您的账户以继续使用</p>
      </div>

      <Card className="shadow-xl border border-gray-100 bg-white/80 backdrop-blur-sm">
        <CardHeader className="sr-only">
          <CardTitle>登录</CardTitle>
          <CardDescription>登录表单</CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit(onLogin)} className="space-y-5">
            {/* Success Message */}
            {successMessage && (
              <div className="bg-success/10 border border-success/30 text-success px-4 py-3 rounded-xl text-sm flex items-center gap-2 animate-in fade-in slide-in-from-top-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="bg-error/10 border border-error/30 text-error px-4 py-3 rounded-xl text-sm animate-in fade-in slide-in-from-top-2">
                {error}
              </div>
            )}

            {/* Account Input */}
            <Field data-invalid={Boolean(errors.account)}>
              <FieldLabel htmlFor="account" className="text-gray-700">
                邮箱
              </FieldLabel>
              <FieldContent>
                <Input
                  id="account"
                  type="text"
                  placeholder="请输入邮箱"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.account)}
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  {...register("account", {
                    required: "请输入邮箱",
                    pattern: {
                      value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                      message: "邮箱格式不正确",
                    },
                  })}
                />
                <FieldError errors={[errors.account]} className="text-xs text-error" />
              </FieldContent>
            </Field>

            {/* Password Input */}
            <Field data-invalid={Boolean(errors.password)}>
              <FieldLabel htmlFor="password" className="text-gray-700">
                密码
              </FieldLabel>
              <FieldContent>
                <Input
                  id="password"
                  type="password"
                  placeholder="请输入密码"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.password)}
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  {...register("password", { required: "请输入密码" })}
                />
                <FieldError errors={[errors.password]} className="text-xs text-error" />
              </FieldContent>
            </Field>

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={isSubmitting || !isValid}
              className="w-full h-12 bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-semibold text-base shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 transition-all duration-300 rounded-xl"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  登录中...
                </>
              ) : (
                <>
                  <LogIn className="w-5 h-5 mr-2" />
                  登录
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
              还没有账户？{" "}
              <Link
                to="/register"
                className="text-brand hover:text-brand-dark font-semibold underline-offset-4 hover:underline transition-colors"
              >
                立即注册
              </Link>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default LoginPage;
