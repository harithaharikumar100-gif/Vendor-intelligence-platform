import React, { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, ShieldAlert, CheckCircle, Info } from 'lucide-react';

export default function DimensionCard({ title, weight, score, sources, summary, signals, articles, persons, links, colorHex }) {
  const [expanded, setExpanded] = useState(false);

  const getTierBadge = (s) => {
    if (s <= 24) return { label: 'Low', bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' };
    if (s <= 49) return { label: 'Medium', bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30' };
    if (s <= 74) return { label: 'High', bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' };
    return { label: 'Critical', bg: 'bg-rose-500/15', text: 'text-rose-400', border: 'border-rose-500/30' };
  };

  const tier = getTierBadge(score);

  return (
    <div className="bg-surface border border-border hover:border-border-light rounded-xl transition-all duration-200 overflow-hidden shadow-lg mb-4">
      {/* Card Header */}
      <div 
        className="p-5 flex items-center justify-between cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colorHex }} />
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight">{title}</h3>
              <span className="text-xs text-slate-400 font-medium">({weight})</span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">{sources}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-2xl font-extrabold font-mono text-white leading-none">
              {score}
            </span>
            <span className="text-xs text-slate-500 font-mono">/100</span>
            <div className="mt-1">
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${tier.border} ${tier.bg} ${tier.text}`}>
                {tier.label}
              </span>
            </div>
          </div>
          <button className="p-1 rounded-lg hover:bg-slate-800 text-slate-400">
            {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>
        </div>
      </div>

      {/* Primary Assessment Quote */}
      <div className="px-5 pb-4">
        <p className="text-sm text-slate-300 leading-relaxed bg-slate-900/60 p-3.5 rounded-lg border border-slate-800/80">
          <span className="font-semibold text-slate-100">Assessment: </span>
          {summary || 'Standard operating posture verified across primary databases.'}
        </p>
      </div>

      {/* Expandable Signal Breakdown */}
      {expanded && (
        <div className="px-5 pb-5 pt-1 border-t border-border/80 space-y-4 text-xs">
          {/* Financial / Cyber / Compliance Signals */}
          {signals && signals.length > 0 && (
            <div>
              <p className="font-bold uppercase tracking-wider text-slate-400 text-[11px] mb-2">
                Identified Risk Signals & Taxonomy:
              </p>
              <div className="space-y-1.5">
                {signals.map((s, idx) => (
                  <div key={idx} className="flex items-start gap-2 p-2 rounded-lg bg-slate-900/40 border border-slate-800">
                    <span className="font-bold text-sky-400 shrink-0">[{s.category || s.authority || 'Signal'}]</span>
                    <span className="text-slate-300 flex-1">{s.indicator || s.action}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0 ${
                      s.severity === 'Critical' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40' :
                      s.severity === 'High' ? 'bg-orange-500/20 text-orange-300 border border-orange-500/40' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      {s.severity || 'Info'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Reputational Adverse Media */}
          {articles && articles.length > 0 && (
            <div>
              <p className="font-bold uppercase tracking-wider text-slate-400 text-[11px] mb-2">
                Adverse Media Articles (36m Horizon):
              </p>
              <div className="space-y-1.5">
                {articles.map((a, idx) => (
                  <div key={idx} className="p-2 rounded-lg bg-slate-900/40 border border-slate-800 flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-slate-200">{a.headline}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">{a.source} • {a.date}</p>
                    </div>
                    {a.url && (
                      <a href={a.url} target="_blank" rel="noreferrer" className="text-sky-400 hover:text-sky-300 p-1">
                        <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Key Persons */}
          {persons && persons.length > 0 && (
            <div>
              <p className="font-bold uppercase tracking-wider text-slate-400 text-[11px] mb-2">
                Executive & Governance Register:
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {persons.map((p, idx) => (
                  <div key={idx} className="p-2.5 rounded-lg bg-slate-900/40 border border-slate-800">
                    <p className="font-bold text-slate-100">{p.name}</p>
                    <p className="text-slate-400 text-[11px]">{p.role} • {p.tenure || 'Established'}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {p.flags?.map((f, i) => (
                        <span key={i} className={`px-1.5 py-0.2 rounded text-[10px] ${f === 'Clean' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/20 text-rose-300'}`}>
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verified Evidence Links */}
          {links && links.length > 0 && (
            <div className="pt-2">
              <p className="font-bold uppercase tracking-wider text-slate-400 text-[10px] mb-1.5">
                Verified Source Attributions:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {links.map((url, i) => {
                  const domain = url.includes('://') ? url.split('/')[2] : url;
                  return (
                    <a
                      key={i}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-sky-500/10 border border-sky-500/20 text-sky-400 hover:bg-sky-500/20 hover:text-sky-300 text-[11px] transition-colors"
                    >
                      <ExternalLink size={11} />
                      {domain}
                    </a>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
