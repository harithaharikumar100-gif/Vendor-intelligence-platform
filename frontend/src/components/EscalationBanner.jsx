import React from 'react';
import { AlertTriangle } from 'lucide-react';

export default function EscalationBanner({ escalations = [] }) {
  if (!escalations || escalations.length === 0) return null;

  return (
    <div className="bg-rose-950/40 border border-rose-500/40 rounded-xl p-4 mb-6 shadow-xl">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 shrink-0 mt-0.5">
          <AlertTriangle size={20} />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-bold text-rose-300 uppercase tracking-wider">
            Automatic Senior Risk Review Escalation Triggered (SK-VDD-001 Section 10.1)
          </h4>
          <p className="text-xs text-rose-200/80 mt-0.5">
            The platform identified critical conditions requiring mandatory human validation before onboarding:
          </p>
          <ul className="mt-2 space-y-1 text-xs text-rose-200">
            {escalations.map((esc, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                <span className="font-semibold">{esc}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
