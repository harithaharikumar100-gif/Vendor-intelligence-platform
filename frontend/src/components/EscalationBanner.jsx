import React from 'react';
import { AlertTriangle } from 'lucide-react';

export default function EscalationBanner({ escalations = [] }) {
  if (!escalations || escalations.length === 0) return null;

  return (
    <div className="border border-tier-critical/25 bg-tier-critical/[0.04] rounded-2xl p-4 shadow-subtle animate-fade-up">
      <div className="flex items-start gap-3">
        <AlertTriangle size={16} className="text-tier-critical shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-[13px] font-medium text-ink-50">
            Automatic senior risk review escalation triggered
            <span className="text-ink-500 font-normal"> · SK-VDD-001 Section 10.1</span>
          </h4>
          <p className="text-xs text-ink-400 mt-1">
            The platform identified critical conditions requiring mandatory human validation before onboarding:
          </p>
          <ul className="mt-2.5 space-y-1.5 text-xs text-ink-200">
            {escalations.map((esc, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="w-1 h-1 rounded-full bg-tier-critical mt-1.5 shrink-0" />
                <span>{esc}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
