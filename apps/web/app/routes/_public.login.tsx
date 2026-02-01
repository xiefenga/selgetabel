import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, LogIn, CheckCircle2 } from "lucide-react";
import { useNavigate, Link, useLocation } from "react-router";

import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";

import { login } from "~/api/auth";
import { useAuthStore } from "~/stores/auth";

import type { FormEvent } from "react";
import type { Route } from "./+types/_auth-pages.login";

export function meta({ }: Route.MetaArgs) {
  return [
    { title: "登录 - LLM Excel" },
    { name: "description", content: "登录到 LLM Excel 系统" },
  ];
}

const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { setUser } = useAuthStore();
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // 检查是否有注册成功的消息
  useEffect(() => {
    const state = location.state as { message?: string } | null;
    if (state?.message) {
      setSuccessMessage(state.message);
      // 清除 location state，避免刷新后仍显示
      window.history.replaceState({}, document.title);
    }
  }, [location]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const userInfo = await login({ account, password });
      // 更新 store 中的用户信息
      setUser(userInfo);
      // 使 react-query 缓存失效，触发重新获取
      await queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      // 登录成功，跳转到首页
      navigate("/");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "登录失败，请重试";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="shadow-2xl border-0 bg-white/90 backdrop-blur-sm">
      <CardHeader className="space-y-2 pb-6">
        <CardTitle className="text-3xl font-bold text-gray-900 text-center">欢迎回来</CardTitle>
        <CardDescription className="text-base text-gray-600 text-center">
          登录您的账户以继续使用
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Success Message */}
          {successMessage && (
            <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3 rounded-lg text-sm flex items-center gap-2 animate-in fade-in slide-in-from-top-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-2">
              {error}
            </div>
          )}

          {/* Account Input */}
          <div className="space-y-2">
            <label htmlFor="account" className="text-sm font-semibold text-gray-800">
              账户
            </label>
            <Input
              id="account"
              type="text"
              placeholder="邮箱或用户名"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              disabled={isLoading}
              required
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
            />
          </div>

          {/* Password Input */}
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-semibold text-gray-800">
              密码
            </label>
            <Input
              id="password"
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              required
              className="h-11 border-gray-300 focus:border-emerald-500 focus:ring-emerald-500"
            />
          </div>

          {/* Submit Button */}
          <Button
            type="submit"
            disabled={isLoading || !account || !password}
            className="w-full h-11 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-base shadow-lg hover:shadow-xl transition-all duration-200"
          >
            {isLoading ? (
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

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            还没有账户？{" "}
            <Link
              to="/register"
              className="text-emerald-600 hover:text-emerald-700 font-semibold underline-offset-4 hover:underline transition-colors"
            >
              立即注册
            </Link>
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

export default LoginPage;
