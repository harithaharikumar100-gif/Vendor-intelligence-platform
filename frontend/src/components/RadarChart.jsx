import React from 'react';
import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip
} from 'recharts';

export default function RadarChart({ scores }) {
  const data = [
    { subject: 'Financial (30%)', value: scores?.financial ?? 20, fullMark: 100 },
    { subject: 'Reputation (20%)', value: scores?.reputation ?? 20, fullMark: 100 },
    { subject: 'Key-Person (20%)', value: scores?.key_person ?? 20, fullMark: 100 },
    { subject: 'Cyber & Tech (20%)', value: scores?.cyber ?? 20, fullMark: 100 },
    { subject: 'Compliance (10%)', value: scores?.compliance ?? 20, fullMark: 100 },
  ];

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <RechartsRadar cx="50%" cy="50%" outerRadius="75%" data={data}>
          <PolarGrid stroke="#1f1f1f" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fill: '#8a8a8a', fontSize: 11, fontFamily: 'Inter' }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={{ fill: '#6b6b6b', fontSize: 9 }}
            stroke="#1f1f1f"
          />
          <Radar
            name="Vendor Risk"
            dataKey="value"
            stroke="#fafafa"
            fill="#fafafa"
            fillOpacity={0.08}
            dot={{ r: 3, fill: '#fafafa' }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const d = payload[0].payload;
                return (
                  <div className="bg-surface-card border border-border-light px-3 py-1.5 rounded-lg text-xs">
                    <p className="font-medium text-ink-50">{d.subject}</p>
                    <p className="text-ink-400">Score: <span className="font-mono font-medium text-ink-50">{d.value}</span> / 100</p>
                  </div>
                );
              }
              return null;
            }}
          />
        </RechartsRadar>
      </ResponsiveContainer>
    </div>
  );
}
