import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { Loader2, UserPlus, Mail, User, Lock } from "lucide-react";

import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";

import { register } from "~/api/auth";

import type { FormEvent } from "react";
import type { Route } from "./+types/_auth-pages.register";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "注册 - LLM Excel" },
    { name: "description", content: "注册 LLM Excel 账户" },
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
    <Card className="shadow-2xl border-0 bg-white/90 backdrop-blur-sm">
      <CardHeader className="space-y-2 pb-6">
        <CardTitle className="text-3xl font-bold text-gray-900 text-center">创建账户</CardTitle>
        <CardDescription className="text-base text-gray-600 text-center">
          填写以下信息以开始使用
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-2">
              {error}
            </div>
          )}

          {/* Username Input */}
          <div className="space-y-2">
            <label htmlFor="username" className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <User className="w-4 h-4 text-gray-500" />
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
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
              minLength={2}
            />
          </div>

          {/* Email Input */}
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <Mail className="w-4 h-4 text-gray-500" />
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
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
            />
          </div>

          {/* Password Input */}
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <Lock className="w-4 h-4 text-gray-500" />
              密码
            </label>
            <Input
              id="password"
              type="password"
              placeholder="至少 6 位字符"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              required
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
              minLength={6}
            />
          </div>

          {/* Confirm Password Input */}
          <div className="space-y-2">
            <label htmlFor="confirmPassword" className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <Lock className="w-4 h-4 text-gray-500" />
              确认密码
            </label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="请再次输入密码"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
              required
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
              minLength={6}
            />
          </div>

          {/* Submit Button */}
          <Button
            type="submit"
            disabled={isLoading || !username || !email || !password || !confirmPassword}
            className="w-full h-11 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-base shadow-lg hover:shadow-xl transition-all duration-200"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                注册中...
              </>
            ) : (
              <>
                <UserPlus className="w-5 h-5 mr-2" />
                注册
              </>
            )}
          </Button>
        </form>

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            已有账户？{" "}
            <Link
              to="/login"
              className="text-emerald-600 hover:text-emerald-700 font-semibold underline-offset-4 hover:underline transition-colors"
            >
              立即登录
            </Link>
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default RegisterPage;
