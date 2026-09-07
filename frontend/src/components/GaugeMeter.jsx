import React from 'react';

export default function GaugeMeter({ score = 20, rating = 'Low', traffic = 'Green' }) {
  const cleanScore = Math.max(0, Math.min(100, Math.round(score)));
  
  // 4-Tier color mapping
  const getTheme = (s) => {
    if (s <= 24) return { text: 'text-emerald-400', stroke: '#10b981', bg: 'rgba(16, 185, 129, 0.12)', border: 'border-emerald-500/30' };
    if (s <= 49) return { text: 'text-amber-400', stroke: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: 'border-amber-500/30' };
    if (s <= 74) return { text: 'text-orange-400', stroke: '#f97316', bg: 'rgba(249, 115, 22, 0.14)', border: 'border-orange-500/30' };
    return { text: 'text-rose-400', stroke: '#ef4444', bg: 'rgba(239, 68, 68, 0.18)', border: 'border-rose-500/30' };
  };

  const theme = getTheme(cleanScore);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (cleanScore / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center p-4">
      <div className="relative w-36 h-36 flex items-center justify-center">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 128 128">
          {/* Background circle */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke="#1a233a"
            strokeWidth="9"
            fill="transparent"
          />
          {/* Progress circle */}
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke={theme.stroke}
            strokeWidth="9"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            fill="transparent"
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className={`text-4xl font-extrabold font-mono tracking-tight ${theme.text}`}>
            {cleanScore}
          </span>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mt-0.5">
            / 100
          </span>
        </div>
      </div>
      
      <div className="mt-3 text-center">
        <span className={`inline-block px-3 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider border ${theme.border} ${theme.text}`} style={{ backgroundColor: theme.bg }}>
          {rating} Risk • {traffic}
        </span>
      </div>
    </div>
  );
}
