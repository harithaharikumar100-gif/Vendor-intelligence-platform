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
          <PolarGrid stroke="#1a233a" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'Plus Jakarta Sans' }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={{ fill: '#64748b', fontSize: 9 }}
            stroke="#1a233a"
          />
          <Radar
            name="Vendor Risk"
            dataKey="value"
            stroke="#38bdf8"
            fill="#38bdf8"
            fillOpacity={0.25}
            dot={{ r: 4, fill: '#38bdf8' }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const d = payload[0].payload;
                return (
                  <div className="bg-slate-900 border border-slate-700 px-3 py-1.5 rounded-lg shadow-xl text-xs">
                    <p className="font-semibold text-sky-400">{d.subject}</p>
                    <p className="text-slate-200">Score: <span className="font-mono font-bold">{d.value}</span> / 100</p>
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
