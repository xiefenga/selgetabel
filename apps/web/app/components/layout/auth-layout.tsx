import { Logo } from "~/components/logo";

import type { PropsWithChildren } from "react";

import DataFlowAnimation from "~/features/auth/data-flow-animation";

export function AuthLayout({ children }: PropsWithChildren) {
  return (
    <div className="h-screen flex relative overflow-hidden bg-gray-50">
      {/* CSS Animations */}
      <style>{`
        @keyframes dataFlowVertical {
          0% { transform: translateY(-100%); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateY(100%); opacity: 0; }
        }
        @keyframes dataFlowHorizontal {
          0% { transform: translateX(-100%); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateX(100%); opacity: 0; }
        }
        @keyframes floatDot {
          0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.6; }
          50% { transform: translate(10px, -15px) scale(1.2); opacity: 1; }
        }
        @keyframes pulseGlow {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.1); opacity: 0.5; }
        }
        @keyframes slideInLeft {
          from { transform: translateX(-20px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideInRight {
          from { transform: translateX(20px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes fadeInUp {
          from { transform: translateY(20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>

      {/* Left Panel - Brand Showcase */}
      <div className="hidden lg:flex lg:w-[55%] xl:w-[60%] relative bg-linear-to-br from-gray-900 via-gray-800 to-gray-900">
        {/* 数据流动画背景 */}
        <DataFlowAnimation />

        {/* 内容区域 */}
        <div className="relative z-10 flex flex-col justify-between px-12 py-8 w-full">
          {/* Logo */}
          <div
            className="flex items-center gap-1"
            style={{
              animation: 'slideInLeft 0.5s ease-out forwards',
            }}
          >
            <Logo size={45} />
            <h1 className="text-3xl font-bold bg-linear-to-r from-emerald-400 via-teal-400 to-blue-400 bg-clip-text text-transparent">
              Selgetabel
            </h1>
          </div>

          {/* 中间主要内容 */}
          <div className="flex-1 flex flex-col justify-center max-w-lg">
            <h2
              className="text-4xl xl:text-5xl font-bold text-white leading-tight mb-6"
              style={{
                animation: 'fadeInUp 0.6s ease-out forwards',
                animationDelay: '0.2s',
                opacity: 0,
              }}
            >
              AI 驱动的
              <br />
              <span className="bg-linear-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
                Excel 智能处理
              </span>
            </h2>
            <p
              className="text-lg text-white/60 leading-relaxed"
              style={{
                animation: 'fadeInUp 0.6s ease-out forwards',
                animationDelay: '0.3s',
                opacity: 0,
              }}
            >
              用自然语言描述需求，AI 生成可执行操作并输出 Excel 公式，
              结果 100% 可复现，告别繁琐的公式编写。
            </p>
          </div>

          {/* 底部 */}
          <div
            className="text-white/40 text-sm"
            style={{
              animation: 'fadeInUp 0.5s ease-out forwards',
              animationDelay: '0.8s',
              opacity: 0,
            }}
          >
            © 2026 Selgetabel. 让数据处理更简单。
          </div>
        </div>
      </div>

      {/* Right Panel - Auth Form */}
      <div className="flex-1 flex flex-col min-h-screen relative">
        {/* 右侧装饰背景 */}
        <div className="absolute inset-0 pointer-events-none">
          <div
            className="absolute top-0 right-0 w-96 h-96 rounded-full opacity-60"
            style={{
              background: 'radial-gradient(circle, rgba(16, 185, 129, 0.08) 0%, transparent 70%)',
            }}
          />
          <div
            className="absolute bottom-0 left-0 w-80 h-80 rounded-full opacity-40"
            style={{
              background: 'radial-gradient(circle, rgba(59, 130, 246, 0.06) 0%, transparent 70%)',
            }}
          />
        </div>

        {/* Mobile Logo Header */}
        <header className="lg:hidden w-full px-6 py-6 flex items-center justify-center relative z-20">
          <div className="flex items-center gap-2">
            <Logo size={40} />
            <h1 className="text-2xl font-bold bg-linear-to-r from-emerald-600 via-teal-600 to-blue-600 bg-clip-text text-transparent">
              Selgetabel
            </h1>
          </div>
        </header>

        {/* Form Container */}
        <div className="flex-1 flex items-center justify-center p-6 sm:p-8 lg:p-12 relative z-10">
          <div
            className="w-full max-w-md"
            style={{
              animation: 'slideInRight 0.5s ease-out forwards',
            }}
          >
            {children}
          </div>
        </div>

        {/* Mobile Footer */}
        <footer className="lg:hidden px-6 py-4 text-center text-gray-400 text-sm">
          © 2026 Selgetabel
        </footer>
      </div>
    </div>
  );
}
