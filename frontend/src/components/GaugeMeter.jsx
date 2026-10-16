import React from 'react';

export default function GaugeMeter({ score = null, rating = 'Not assessed', traffic = 'Unrated' }) {
  const assessed = Number.isFinite(score);
  const cleanScore = Math.max(0, Math.min(100, Math.round(score)));

  // 4-Tier color mapping — the only color in this component; everything else is monochrome.
  const getTheme = (s) => {
    if (rating === 'Low') return { text: 'text-tier-low', stroke: '#22c55e' };
    if (rating === 'Medium') return { text: 'text-tier-medium', stroke: '#eab308' };
    if (rating === 'High') return { text: 'text-tier-high', stroke: '#f97316' };
    return { text: 'text-tier-critical', stroke: '#ef4444' };
  };

  const theme = assessed ? getTheme(cleanScore) : {text: 'text-ink-500', stroke: '#6b6b6b'};
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (cleanScore / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative w-36 h-36 flex items-center justify-center">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 128 128">
          <circle cx="64" cy="64" r={radius} stroke="rgba(255,255,255,0.06)" strokeWidth="4" fill="transparent" />
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke={theme.stroke}
            strokeWidth="4"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            fill="transparent"
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-3xl font-semibold font-mono tracking-tight text-ink-50">
            {assessed ? cleanScore : '—'}
          </span>
          <span className="text-[10px] font-medium uppercase tracking-wider text-ink-500 mt-0.5">
            / 100
          </span>
        </div>
      </div>

      <div className="mt-3 text-center">
        <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider ${theme.text}`}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: theme.stroke }} />
          {assessed ? `${rating} · Provisional` : 'Not assessed'}
        </span>
      </div>
    </div>
  );
}
