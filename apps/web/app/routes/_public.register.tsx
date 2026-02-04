import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { Loader2, UserPlus, Mail, User, Lock } from "lucide-react";

import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";

import { register } from "~/api/auth";

import type { FormEvent } from "react";
import type { Route } from "./+types/_public.register";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "注册 - Selgetabel" },
    { name: "description", content: "注册 Selgetabel 账户" },
  ];
}

const RegisterPage = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    // 验证密码确认
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    // 验证密码长度
    if (password.length < 6) {
      setError("密码长度至少为 6 位");
      return;
    }

    setIsLoading(true);

    try {
      await register({ username, email, password });
      // 注册成功，跳转到登录页
      navigate("/login", {
        replace: true,
        state: { message: "注册成功，请登录" }
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "注册失败，请重试";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
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
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Error Message */}
            {error && (
              <div className="bg-error/10 border border-error/30 text-error px-4 py-3 rounded-xl text-sm animate-in fade-in slide-in-from-top-2">
                {error}
              </div>
            )}

            {/* Username Input */}
            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-medium text-gray-700 flex items-center gap-2">
                <User className="w-4 h-4 text-gray-400" />
                用户名
              </label>
              <Input
                id="username"
                type="text"
                placeholder="请输入用户名"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                required
                className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                minLength={2}
              />
            </div>

            {/* Email Input */}
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-gray-700 flex items-center gap-2">
                <Mail className="w-4 h-4 text-gray-400" />
                邮箱
              </label>
              <Input
                id="email"
                type="email"
                placeholder="请输入邮箱地址"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                required
                className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
              />
            </div>

            {/* Password Row - Two columns on larger screens */}
            <div className="grid gap-4 sm:grid-cols-2">
              {/* Password Input */}
              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium text-gray-700 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-gray-400" />
                  密码
                </label>
                <Input
                  id="password"
                  type="password"
                  placeholder="至少 6 位"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  required
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  minLength={6}
                />
              </div>

              {/* Confirm Password Input */}
              <div className="space-y-2">
                <label htmlFor="confirmPassword" className="text-sm font-medium text-gray-700 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-gray-400" />
                  确认密码
                </label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="再次输入"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  required
                  className="h-12 bg-gray-50/50 border-gray-200 focus:border-brand focus:ring-brand/20 focus:bg-white transition-colors rounded-xl"
                  minLength={6}
                />
              </div>
            </div>

            {/* Terms */}
            <p className="text-xs text-gray-400 leading-relaxed">
              注册即表示您同意我们的{" "}
              <button type="button" className="text-brand hover:underline">服务条款</button>
              {" "}和{" "}
              <button type="button" className="text-brand hover:underline">隐私政策</button>
            </p>

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={isLoading || !username || !email || !password || !confirmPassword}
              className="w-full h-12 bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-semibold text-base shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 transition-all duration-300 rounded-xl"
            >
              {isLoading ? (
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

      {/* Trust badges */}
      <div className="flex items-center justify-center gap-6 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
          </svg>
          安全注册
        </span>
        <span className="flex items-center gap-1">
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z" />
          </svg>
          免费试用
        </span>
      </div>
    </div>
  );
};

export default RegisterPage;
