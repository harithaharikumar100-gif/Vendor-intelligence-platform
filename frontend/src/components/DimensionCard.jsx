import React, { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';

const severityDot = (sev) => {
  switch (sev) {
    case 'Critical': return 'bg-tier-critical';
    case 'High': return 'bg-tier-high';
    case 'Elevated': return 'bg-tier-medium';
    default: return 'bg-ink-700';
  }
};

const severityText = (sev) => {
  switch (sev) {
    case 'Critical': return 'text-tier-critical';
    case 'High': return 'text-tier-high';
    case 'Elevated': return 'text-tier-medium';
    default: return 'text-ink-500';
  }
};

const principleDot = (status) => {
  if (status === 'evidence_found') return 'bg-tier-low';
  if (status === 'evidence_of_concern') return 'bg-tier-high';
  return 'bg-ink-700';
};

const principleLabel = (status) => {
  if (status === 'evidence_found') return 'Evidence found';
  if (status === 'evidence_of_concern') return 'Evidence of concern';
  return 'Not disclosed in available sources';
};

const sourceBadge = (source) => {
  if (source === 'ai_synthesis') {
    return { label: 'AI-synthesized', cls: 'text-accent-text border-accent-border bg-accent-muted' };
  }
  return { label: 'Rule-engine fallback', cls: 'text-ink-500 border-border' };
};

export default function DimensionCard({ title, weight, score, sources, summary, signals, articles, persons, links, colorHex, frameworkAlignment, source }) {
  const [expanded, setExpanded] = useState(false);

  const getTierLabel = (s) => {
    if (s <= 24) return { label: 'Low', color: 'text-tier-low' };
    if (s <= 49) return { label: 'Medium', color: 'text-tier-medium' };
    if (s <= 74) return { label: 'High', color: 'text-tier-high' };
    return { label: 'Critical', color: 'text-tier-critical' };
  };

  const tier = getTierLabel(score);

  return (
    <div className="border border-border hover:border-border-light bg-surface rounded-2xl overflow-hidden mb-3 relative transition-colors duration-200">
      <span className={`absolute left-0 top-0 bottom-0 w-0.5 ${tier.color.replace('text-', 'bg-')}`} />
      {/* Card Header */}
      <div className="p-5 flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-medium text-ink-50 tracking-tight">{title}</h3>
            <span className="text-xs text-ink-500">{weight}</span>
            {source && (
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${sourceBadge(source).cls}`}>
                {sourceBadge(source).label}
              </span>
            )}
          </div>
          <p className="text-xs text-ink-500 mt-0.5">{sources}</p>
        </div>

        <div className="text-right shrink-0">
          <span className={`text-xl font-semibold font-mono ${tier.color}`}>{score}</span>
          <span className="text-xs text-ink-500 font-mono">/100</span>
          <div className={`text-[11px] font-medium uppercase tracking-wider mt-0.5 ${tier.color}`}>
            {tier.label}
          </div>
        </div>
      </div>

      {/* Assessment */}
      <div className="px-5 pb-4">
        <p className="text-sm text-ink-200 leading-relaxed">
          <span className="text-ink-500">Assessment — </span>
          {summary || 'Standard operating posture verified across primary databases.'}
        </p>
      </div>

      {/* Risk factors, point by point — always visible */}
      <div className="px-5 pb-4 space-y-5 text-[13px]">
        {signals && signals.length > 0 && (
          <div>
            <p className="text-ink-500 text-[11px] uppercase tracking-wider mb-2">
              Key risk factors ({signals.length})
            </p>
            <ol className="space-y-0">
              {signals.map((s, idx) => (
                <li key={idx} className="flex items-start gap-3 py-2 border-t border-border first:border-t-0">
                  <span className="font-mono text-ink-500 shrink-0 w-5">{idx + 1}.</span>
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${severityDot(s.severity)}`} />
                  <span className="text-ink-200 flex-1">
                    <span className="text-ink-500">[{s.category || s.authority || 'Signal'}]</span> {s.indicator || s.action}
                  </span>
                  <span className={`text-[11px] font-medium uppercase tracking-wide shrink-0 ${severityText(s.severity)}`}>
                    {s.severity || 'Info'}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {articles && articles.length > 0 && (
          <div>
            <p className="text-ink-500 text-[11px] uppercase tracking-wider mb-2">
              Key risk factors — adverse media, 36m horizon ({articles.length})
            </p>
            <ol className="space-y-0">
              {articles.map((a, idx) => (
                <li key={idx} className="flex items-start gap-3 py-2 border-t border-border first:border-t-0">
                  <span className="font-mono text-ink-500 shrink-0 w-5">{idx + 1}.</span>
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${severityDot(a.severity)}`} />
                  <div className="flex-1">
                    <p className="text-ink-200">{a.headline}</p>
                    <p className="text-[11px] text-ink-500 mt-0.5">{a.source} · {a.date}</p>
                  </div>
                  <span className={`text-[11px] font-medium uppercase tracking-wide shrink-0 ${severityText(a.severity)}`}>
                    {a.severity || 'Info'}
                  </span>
                  {a.url && (
                    <a href={a.url} target="_blank" rel="noreferrer" className="text-ink-500 hover:text-ink-50 shrink-0">
                      <ExternalLink size={13} />
                    </a>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}

        {persons && persons.length > 0 && (
          <div>
            <p className="text-ink-500 text-[11px] uppercase tracking-wider mb-2">
              Executive & governance register ({persons.length})
            </p>
            <ol className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {persons.map((p, idx) => (
                <li key={idx} className="border border-border rounded-lg p-3">
                  <p className="text-ink-50 font-medium">
                    <span className="font-mono text-ink-500 mr-1.5">{idx + 1}.</span>{p.name}
                  </p>
                  <p className="text-ink-500 text-[11px] mt-0.5">{p.role} · {p.tenure || 'Established'}</p>
                  <div className="mt-1.5 flex flex-col gap-1">
                    {p.flags?.map((f, i) => (
                      <span key={i} className="text-[11px] text-ink-400 flex items-start gap-1.5">
                        <span className={`w-1 h-1 rounded-full mt-1.5 shrink-0 ${
                          f.toLowerCase().startsWith('clean') || f.toLowerCase().startsWith('no ') ? 'bg-tier-low' : 'bg-tier-high'
                        }`} />
                        {f}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}
        {frameworkAlignment && frameworkAlignment.length > 0 && frameworkAlignment.map((fw, fwIdx) => (
          <div key={fwIdx}>
            <p className="text-ink-500 text-[11px] uppercase tracking-wider mb-2">
              Framework alignment — {fw.framework}
            </p>
            <ol className="space-y-0">
              {fw.principles.map((p, idx) => (
                <li key={idx} className="flex items-start gap-3 py-2 border-t border-border first:border-t-0">
                  <span className="font-mono text-ink-500 shrink-0 w-5">{idx + 1}.</span>
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${principleDot(p.status)}`} />
                  <span className="text-ink-200 flex-1">{p.title}</span>
                  <span className={`text-[11px] font-medium uppercase tracking-wide shrink-0 ${
                    p.status === 'evidence_of_concern' ? 'text-tier-high' : p.status === 'evidence_found' ? 'text-tier-low' : 'text-ink-500'
                  }`}>
                    {principleLabel(p.status)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>

      {/* Expandable extra detail (evidence source links only) */}
      {links && links.length > 0 && (
        <div className="border-t border-border">
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full px-5 py-3 flex items-center justify-between text-xs text-ink-500 hover:text-ink-200 transition-colors"
          >
            <span>Verified source attributions ({links.length})</span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {expanded && (
            <div className="px-5 pb-4 flex flex-wrap gap-1.5">
              {links.map((url, i) => {
                const domain = url.includes('://') ? url.split('/')[2] : url;
                return (
                  <a
                    key={i}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-border text-ink-400 hover:text-ink-50 hover:border-border-light text-[11px] transition-colors"
                  >
                    <ExternalLink size={11} />
                    {domain}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
