const DataFlowAnimation = () => {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* 网格背景 */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(5, 150, 105, 0.5) 1px, transparent 1px),
            linear-gradient(90deg, rgba(5, 150, 105, 0.5) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      />

      {/* 数据流线条 - 垂直 */}
      {[...Array(6)].map((_, i) => (
        <div
          key={`v-${i}`}
          className="absolute w-px bg-linear-to-b from-transparent via-emerald-500/30 to-transparent"
          style={{
            left: `${15 + i * 15}%`,
            top: '-20%',
            height: '140%',
            animation: `dataFlowVertical ${3 + i * 0.5}s linear infinite`,
            animationDelay: `${i * 0.3}s`,
          }}
        />
      ))}

      {/* 数据流线条 - 水平 */}
      {[...Array(4)].map((_, i) => (
        <div
          key={`h-${i}`}
          className="absolute h-px bg-linear-to-r from-transparent via-blue-500/20 to-transparent"
          style={{
            top: `${20 + i * 20}%`,
            left: '-20%',
            width: '140%',
            animation: `dataFlowHorizontal ${4 + i * 0.7}s linear infinite`,
            animationDelay: `${i * 0.5}s`,
          }}
        />
      ))}

      {/* 浮动数据点 */}
      {[...Array(12)].map((_, i) => (
        <div
          key={`dot-${i}`}
          className="absolute w-1.5 h-1.5 rounded-full"
          style={{
            background: i % 2 === 0 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(59, 130, 246, 0.5)',
            left: `${10 + (i * 7) % 80}%`,
            top: `${5 + (i * 11) % 90}%`,
            animation: `floatDot ${4 + (i % 3)}s ease-in-out infinite`,
            animationDelay: `${i * 0.2}s`,
            boxShadow: i % 2 === 0
              ? '0 0 8px rgba(16, 185, 129, 0.4)'
              : '0 0 8px rgba(59, 130, 246, 0.3)',
          }}
        />
      ))}

      {/* 大光晕 */}
      <div
        className="absolute -top-1/4 -right-1/4 w-[600px] h-[600px] rounded-full opacity-40"
        style={{
          background: 'radial-gradient(circle, rgba(16, 185, 129, 0.15) 0%, transparent 70%)',
          animation: 'pulseGlow 8s ease-in-out infinite',
        }}
      />
      <div
        className="absolute -bottom-1/4 -left-1/4 w-[500px] h-[500px] rounded-full opacity-30"
        style={{
          background: 'radial-gradient(circle, rgba(59, 130, 246, 0.12) 0%, transparent 70%)',
          animation: 'pulseGlow 10s ease-in-out infinite',
          animationDelay: '2s',
        }}
      />
    </div>
  );
}

export default DataFlowAnimation;