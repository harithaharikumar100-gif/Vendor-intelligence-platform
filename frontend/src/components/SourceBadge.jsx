import React from 'react';
import { CheckCircle2, Search, Sparkles } from 'lucide-react';

// Maps financial_fetcher.py's field_sources tags to a visible confidence
// signal, so a structured fact (yfinance/wikidata) isn't shown with the same
// unqualified certainty as an LLM's best-effort recall (llm_estimate) —
// confirmed live this session: CN Rail's founding year flipped between
// correct and wrong across two otherwise-identical runs when it came from
// an LLM guess, with nothing in the UI distinguishing it from a verified fact.
const SOURCE_META = {
  yfinance: { label: 'Verified', title: 'Structured, company-reported data from yfinance', icon: CheckCircle2, color: 'text-tier-low' },
  wikidata: { label: 'Verified', title: 'Structured Wikidata property (deterministic)', icon: CheckCircle2, color: 'text-tier-low' },
  wikipedia_extract: { label: 'Sourced', title: 'Matched from Wikipedia article text — not a structured field', icon: Search, color: 'text-tier-medium' },
  web_scrape: { label: 'Sourced', title: 'Matched from web search results — not independently verified', icon: Search, color: 'text-tier-medium' },
  llm_estimate: { label: 'Estimated', title: 'No verifiable source found — AI best-effort estimate, may be wrong', icon: Sparkles, color: 'text-tier-high' },
};

export default function SourceBadge({ source }) {
  const meta = SOURCE_META[source];
  if (!meta) return null;

  const Icon = meta.icon;
  return (
    <span
      title={meta.title}
      className={`inline-flex items-center gap-0.5 text-[9px] font-medium uppercase tracking-wider shrink-0 ${meta.color}`}
    >
      <Icon size={9} strokeWidth={2} />
      {meta.label}
    </span>
  );
}
