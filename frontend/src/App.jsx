import React, { useState, useEffect, useRef } from 'react';
import {
  Shield, Search, Download, FileText, CheckCircle2, AlertTriangle,
  Building2, Globe, TrendingUp, Key, Cpu, Scale, ChevronRight,
  ExternalLink, Sparkles, Filter, RefreshCw, Layers, ListChecks,
  Users, Clock
} from 'lucide-react';

import GaugeMeter from './components/GaugeMeter';
import RadarChart from './components/RadarChart';
import DimensionCard from './components/DimensionCard';
import EscalationBanner from './components/EscalationBanner';

export default function App() {
  const [vendorInput, setVendorInput] = useState('Shopify Inc.');
  const [industry, setIndustry] = useState('Technology & SaaS');
  const [country, setCountry] = useState('Canada');
  const [companyUrl, setCompanyUrl] = useState('https://www.shopify.com');
  const [ticker, setTicker] = useState('SHOP');
  const [businessNumber, setBusinessNumber] = useState('');
  const [dunsNumber, setDunsNumber] = useState('');
  const [naicsCode, setNaicsCode] = useState('');
  const [concerns, setConcerns] = useState('');

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [presets, setPresets] = useState([]);
  const [normalizedPreview, setNormalizedPreview] = useState('');

  // React 18 StrictMode intentionally double-invokes mount effects in dev
  // to surface side-effect bugs — without this guard, that means every page
  // load silently ran two full due-diligence analyses (double the Groq/
  // Serper quota) for no reason. This ref makes the one-time initial fetch
  // actually run once, in both dev and production.
  const didInit = useRef(false);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    fetch('/api/presets')
      .then((res) => res.json())
      .then((data) => setPresets(data))
      .catch(() => {});

    handleRunAnalysis('Shopify Inc.', 'Technology & SaaS', 'Canada', 'https://www.shopify.com', 'SHOP');
  }, []);

  useEffect(() => {
    if (!vendorInput.trim()) {
      setNormalizedPreview('');
      return;
    }
    fetch('/api/normalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vendor: vendorInput })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.normalized_name && data.normalized_name !== vendorInput.trim()) {
          setNormalizedPreview(data.normalized_name);
        } else {
          setNormalizedPreview('');
        }
      })
      .catch(() => {});
  }, [vendorInput]);

  const handleRunAnalysis = async (
    vName = vendorInput,
    vInd = industry,
    vCountry = country,
    vUrl = companyUrl,
    vTicker = ticker
  ) => {
    if (!vName.trim()) return;

    setLoading(true);
    setError(null);
    setLoadingStep(1);

    const stepInterval = setInterval(() => {
      setLoadingStep((prev) => (prev < 4 ? prev + 1 : prev));
    }, 1200);

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vendor: vName.trim(),
          industry: vInd,
          country: vCountry,
          company_url: vUrl,
          ticker: vTicker,
          business_number: businessNumber,
          duns_number: dunsNumber,
          naics_code: naicsCode,
          concerns: concerns,
        }),
      });

      clearInterval(stepInterval);

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Due diligence analysis failed.');
      }

      const data = await res.json();
      setResult(data);
    } catch (err) {
      clearInterval(stepInterval);
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingStep(0);
    }
  };

  const selectPreset = (p) => {
    setVendorInput(p.name);
    setIndustry(p.industry);
    setCountry(p.country);
    setCompanyUrl(p.domain);
    setTicker(p.ticker);
    handleRunAnalysis(p.name, p.industry, p.country, p.domain, p.ticker);
  };

  const handleDownloadPdf = async () => {
    if (!result) return;
    try {
      const res = await fetch('/api/download-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          result: result,
          vendor_name: result.vendor_name || vendorInput
        })
      });

      if (!res.ok) throw new Error('PDF download failed');

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `DRiskify_SK_VDD_001_${(result.vendor_name || 'vendor').toLowerCase().replace(/\s+/g, '_')}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert(`Error downloading PDF: ${err.message}`);
    }
  };

  const handleExportJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `DRiskify_SK_VDD_001_${(result.vendor_name || 'vendor').toLowerCase().replace(/\s+/g, '_')}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const getTierColor = (rating) => {
    switch (rating) {
      case 'Low': return 'text-tier-low';
      case 'Medium': return 'text-tier-medium';
      case 'High': return 'text-tier-high';
      case 'Critical': return 'text-tier-critical';
      default: return 'text-tier-low';
    }
  };

  // Score -> tier color, for highlighting the numbers that actually matter
  // (dimension scores, confidence) rather than leaving everything monochrome.
  const scoreTierColor = (s) => {
    if (s <= 24) return 'text-tier-low';
    if (s <= 49) return 'text-tier-medium';
    if (s <= 74) return 'text-tier-high';
    return 'text-tier-critical';
  };

  const confidenceColor = (c) => {
    if (c >= 80) return 'text-tier-low';
    if (c >= 60) return 'text-ink-200';
    if (c >= 40) return 'text-tier-medium';
    return 'text-tier-high';
  };

  return (
    <div className="min-h-screen bg-background text-ink-50 flex flex-col font-sans selection:bg-white selection:text-black">
      {/* Top Navigation */}
      <header className="border-b border-border sticky top-0 z-50 bg-background/95 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Shield className="w-4 h-4 text-ink-50" strokeWidth={1.75} />
            <span className="text-sm font-medium tracking-tight text-ink-50">DRiskify</span>
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-border text-ink-500 font-mono">
              SK-VDD-001
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-1.5 text-[11px] text-ink-500">
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low" />
              <span>SEDAR+ · CCCS · OSFI · Live</span>
            </div>
            <button
              onClick={() => handleRunAnalysis()}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg border border-border hover:border-border-light text-ink-200 hover:text-ink-50 text-xs font-medium transition-colors disabled:opacity-40 flex items-center gap-1.5"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Re-scan
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
        {/* Search & Hero */}
        <section className="space-y-5">
          <div>
            <h1 className="text-2xl font-medium text-ink-50 tracking-tight">
              Vendor intelligence scraping & risk scoring
            </h1>
            <p className="text-sm text-ink-500 mt-1.5">
              Autonomous 5-dimension intelligence sweep across Canadian & international public records.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-500" strokeWidth={1.75} />
              <input
                type="text"
                value={vendorInput}
                onChange={(e) => setVendorInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleRunAnalysis()}
                placeholder="Enter vendor legal name (e.g. Shopify Inc., BlackBerry Ltd., CGI Inc.)..."
                className="w-full pl-10 pr-4 py-2.5 bg-surface border border-border rounded-lg text-ink-50 text-sm focus:outline-none focus:border-border-light transition-colors placeholder:text-ink-500"
              />
            </div>

            <button
              onClick={() => handleRunAnalysis()}
              disabled={loading}
              className="px-5 py-2.5 rounded-lg bg-white hover:bg-ink-200 text-black font-medium text-sm transition-colors disabled:opacity-40 flex items-center justify-center gap-2 shrink-0"
            >
              {loading ? <RefreshCw size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Execute due diligence
            </button>
          </div>

          {normalizedPreview && (
            <div className="flex items-center gap-1.5 text-xs text-ink-400 font-mono">
              <CheckCircle2 size={12} />
              <span>Normalised to <span className="text-ink-50">{normalizedPreview}</span> — legal suffix stripped</span>
            </div>
          )}

          <div className="pt-1">
            <span className="text-[11px] text-ink-500 uppercase tracking-wider mr-2">Quick select</span>
            <div className="inline-flex flex-wrap gap-1.5 mt-1.5">
              {presets.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => selectPreset(p)}
                  className="px-2.5 py-1 rounded-md border border-border hover:border-border-light text-ink-400 hover:text-ink-50 text-xs transition-colors"
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>

          <div className="pt-1">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-200 transition-colors"
            >
              <Filter size={12} />
              <span>{showAdvanced ? 'Hide' : 'Show'} advanced identifiers (CRA BN, TSX ticker, domain, DUNS, NAICS)</span>
            </button>

            {showAdvanced && (
              <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3 mt-3 p-4 border border-border rounded-lg text-xs">
                <div>
                  <label className="block text-ink-500 mb-1">Industry domain</label>
                  <input
                    type="text"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                    className="w-full px-3 py-2 bg-surface-card border border-border rounded-md text-ink-200 focus:outline-none focus:border-border-light"
                  />
                </div>
                <div>
                  <label className="block text-ink-500 mb-1">CRA business number (9-digit)</label>
                  <input
                    type="text"
                    value={businessNumber}
                    onChange={(e) => setBusinessNumber(e.target.value)}
                    placeholder="e.g. 123456789"
                    className="w-full px-3 py-2 bg-surface-card border border-border rounded-md text-ink-200 focus:outline-none focus:border-border-light placeholder:text-ink-700"
                  />
                </div>
                <div>
                  <label className="block text-ink-500 mb-1">Stock ticker (TSX/NYSE)</label>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value)}
                    placeholder="e.g. SHOP, BB"
                    className="w-full px-3 py-2 bg-surface-card border border-border rounded-md text-ink-200 focus:outline-none focus:border-border-light placeholder:text-ink-700"
                  />
                </div>
                <div>
                  <label className="block text-ink-500 mb-1">D&B D-U-N-S number</label>
                  <input
                    type="text"
                    value={dunsNumber}
                    onChange={(e) => setDunsNumber(e.target.value)}
                    placeholder="e.g. 204958581"
                    className="w-full px-3 py-2 bg-surface-card border border-border rounded-md text-ink-200 focus:outline-none focus:border-border-light placeholder:text-ink-700"
                  />
                </div>
                <div>
                  <label className="block text-ink-500 mb-1">NAICS code</label>
                  <input
                    type="text"
                    value={naicsCode}
                    onChange={(e) => setNaicsCode(e.target.value)}
                    placeholder="e.g. 511210"
                    className="w-full px-3 py-2 bg-surface-card border border-border rounded-md text-ink-200 focus:outline-none focus:border-border-light placeholder:text-ink-700"
                  />
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Loading State */}
        {loading && (
          <div className="border border-border rounded-xl p-8 text-center space-y-3">
            <RefreshCw size={20} className="animate-spin mx-auto text-ink-400" />
            <div>
              <h3 className="text-sm font-medium text-ink-50">
                Gathering autonomous intelligence on {vendorInput}...
              </h3>
              <p className="text-xs text-ink-500 font-mono mt-1.5">
                {loadingStep === 1 && '1/4 · Input normalisation & CBCA jurisdiction resolution'}
                {loadingStep === 2 && '2/4 · Querying SEDAR+, Tier-1 Canadian media & CanLII'}
                {loadingStep === 3 && '3/4 · Inspecting CCCS advisories, CISA KEV & OSFI/FINTRAC'}
                {loadingStep >= 4 && '4/4 · Applying SK-VDD-001 signal taxonomy & AI synthesis'}
              </p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-4 rounded-lg border border-tier-critical/25 bg-tier-critical/[0.04] text-tier-critical text-sm flex items-center gap-3">
            <AlertTriangle size={16} className="shrink-0" />
            <div><strong>Error —</strong> {error}</div>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-8">
            <EscalationBanner escalations={result.automatic_escalations} />

            {/* Executive Hero */}
            <div className="border border-border rounded-xl p-6 flex flex-col md:flex-row items-center justify-between gap-6">
              <div className="space-y-2 flex-1">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-xl font-medium text-ink-50 tracking-tight">
                    {result.vendor_name || vendorInput}
                  </h2>
                  <span className={`text-xs font-medium uppercase tracking-wider ${getTierColor(result.overall_risk_rating)}`}>
                    {result.overall_risk_rating} risk · {result.traffic_light}
                  </span>
                </div>
                <p className="text-xs text-ink-500">
                  Jurisdiction: <span className="text-ink-200">{result.registration_country}</span> · Industry: <span className="text-ink-200">{result.company_profile?.industry || industry}</span> · Data confidence: <span className={`font-medium ${confidenceColor(result.confidence_score)}`}>{result.confidence_score}%</span> (36m horizon)
                </p>
                <p className="text-xs text-ink-300 pt-1">
                  <span className="text-ink-500">Recommended action — </span>
                  {result.recommended_action}
                </p>
              </div>

              <div className="shrink-0 border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-6">
                <GaugeMeter
                  score={result.overall_score}
                  rating={result.overall_risk_rating}
                  traffic={result.traffic_light}
                />
              </div>
            </div>

            {/* Entity Intelligence Quick Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-border rounded-xl overflow-hidden border border-border">
              {[
                { icon: Key, label: 'Executive leadership', value: result.company_profile?.ceo, iconColor: 'text-violet-400' },
                { icon: Building2, label: 'Corporate founder', value: result.company_profile?.founder, iconColor: 'text-sky-400' },
                { icon: Clock, label: 'Incorporated', value: result.company_profile?.founded, iconColor: 'text-ink-400' },
                { icon: Globe, label: 'Headquarters', value: result.company_profile?.headquarters, iconColor: 'text-amber-400' },
                { icon: Users, label: 'Est. employees', value: result.company_profile?.employees, iconColor: 'text-ink-400' },
                { icon: TrendingUp, label: 'Annual revenue', value: result.company_profile?.financial_metrics?.revenue, mono: true, iconColor: 'text-tier-low', valueColor: 'text-tier-low' },
              ].map((cell, i) => (
                <div key={i} className="bg-surface p-3.5 flex flex-col justify-between gap-1.5">
                  <span className="text-[10px] uppercase text-ink-500 tracking-wider flex items-center gap-1.5">
                    <cell.icon size={11} strokeWidth={1.75} className={cell.iconColor} /> {cell.label}
                  </span>
                  <span className={`text-xs font-medium truncate ${cell.mono ? 'font-mono' : ''} ${cell.value ? (cell.valueColor || 'text-ink-50') : 'text-ink-500'}`} title={cell.value}>
                    {cell.value || (cell.label === 'Annual revenue' ? 'Private / unlisted' : 'Not available')}
                  </span>
                </div>
              ))}
            </div>

            {/* 5-Dimension Mini Bar */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-border rounded-xl overflow-hidden border border-border">
              {[
                { key: 'financial', label: 'Financial viability', wt: '30%' },
                { key: 'reputation', label: 'Reputational risk', wt: '20%' },
                { key: 'key_person', label: 'Key-person & gov', wt: '20%' },
                { key: 'cyber', label: 'Technology & cyber', wt: '20%' },
                { key: 'compliance', label: 'Regulatory compliance', wt: '10%' },
              ].map((dim) => {
                const s = result.risk_scores?.[dim.key] ?? 20;
                return (
                  <div key={dim.key} className="bg-surface p-4 relative">
                    <span className={`absolute left-0 top-0 bottom-0 w-0.5 ${scoreTierColor(s).replace('text-', 'bg-')}`} />
                    <div className="flex items-center justify-between text-[11px] text-ink-500 uppercase tracking-wider mb-2">
                      <span>{dim.label}</span>
                      <span className="text-ink-700">{dim.wt}</span>
                    </div>
                    <div className="flex items-baseline justify-between">
                      <span className={`text-xl font-semibold font-mono ${scoreTierColor(s)}`}>{s}</span>
                      <span className="text-[11px] text-ink-500 font-mono">/100</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Tab Navigation */}
            <div className="border-b border-border flex items-center gap-1 overflow-x-auto">
              {[
                { id: 'overview', label: 'Executive overview' },
                { id: 'dimensions', label: '5 risk dimensions' },
                { id: 'corporate', label: 'Corporate registry & filings' },
                { id: 'mitigation', label: 'Mitigations & data gaps' },
                { id: 'export', label: 'Official export center' },
              ].map((t) => {
                const active = activeTab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-4 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                      active
                        ? 'border-white text-ink-50'
                        : 'border-transparent text-ink-500 hover:text-ink-200'
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>

            {/* TAB 1: Executive Overview */}
            {activeTab === 'overview' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-6 border border-border rounded-xl p-6">
                  <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider mb-4">
                    5-dimension risk radar
                  </h3>
                  <RadarChart scores={result.risk_scores} />
                </div>

                <div className="lg:col-span-6 space-y-4">
                  <div className="border border-border rounded-xl p-6 space-y-3">
                    <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Holistic analyst assessment · Section 8
                    </h3>
                    <p className="text-sm text-ink-200 leading-relaxed">
                      {result.analyst_notes}
                    </p>
                  </div>

                  <div className="border border-border rounded-xl p-6 space-y-3">
                    <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Authoritative sources ingested · Section 5
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {result.data_sources_used?.map((src, i) => (
                        <span key={i} className="px-2.5 py-1 rounded-md border border-border text-[11px] text-ink-400">
                          {src}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: 5 Risk Dimensions */}
            {activeTab === 'dimensions' && (
              <div className="space-y-3">
                <DimensionCard
                  title="Financial viability risk"
                  weight="30% weight"
                  score={result.risk_scores?.financial ?? 20}
                  sources="SEDAR+ filings, CBCA registry, solvency, liquidity ratios"
                  summary={result.explanations?.financial?.summary}
                  signals={result.explanations?.financial?.signals}
                  links={result.evidence_links?.financial}
                />

                <DimensionCard
                  title="Reputational risk"
                  weight="20% weight"
                  score={result.risk_scores?.reputation ?? 20}
                  sources="CBC, Globe and Mail, Financial Post, CanLII litigation (36m)"
                  summary={result.explanations?.reputation?.summary}
                  articles={result.explanations?.reputation?.articles}
                  links={result.evidence_links?.reputation}
                />

                <DimensionCard
                  title="Key-person & governance risk"
                  weight="20% weight"
                  score={result.risk_scores?.key_person ?? 20}
                  sources="SEDI insiders, LinkedIn, OFAC/OSFI sanctions lists, CanLII"
                  summary={result.explanations?.key_person?.summary}
                  persons={result.explanations?.key_person?.persons}
                  links={result.evidence_links?.key_person}
                />

                <DimensionCard
                  title="Technology & cybersecurity risk"
                  weight="20% weight"
                  score={result.risk_scores?.cyber ?? 20}
                  sources="CCCS (cyber.gc.ca), CISA KEV, NVD (CVSS ≥ 7.0), HIBP"
                  summary={result.explanations?.cyber?.summary}
                  signals={result.explanations?.cyber?.signals}
                  links={result.evidence_links?.cyber}
                />

                <DimensionCard
                  title="Regulatory compliance risk"
                  weight="10% weight"
                  score={result.risk_scores?.compliance ?? 20}
                  sources="OSFI enforcement, FINTRAC AMPs, CSA orders, OPC PIPEDA, CRTC"
                  summary={result.explanations?.compliance?.summary}
                  signals={result.explanations?.compliance?.signals}
                  links={result.evidence_links?.compliance}
                />
              </div>
            )}

            {/* TAB 3: Corporate Registry & Filings */}
            {activeTab === 'corporate' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="border border-border rounded-xl p-6 space-y-4">
                  <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Corporate entity verification
                  </h3>
                  <div className="divide-y divide-border text-xs">
                    {[
                      { k: 'Legal entity name', v: result.vendor_name },
                      { k: 'Jurisdiction', v: result.registration_country },
                      { k: 'CRA business number', v: result.business_number || 'Inferred via registry' },
                      { k: 'Executive leadership (CEO)', v: result.company_profile?.ceo || 'Not available' },
                      { k: 'Corporate founder', v: result.company_profile?.founder || 'Not available' },
                      { k: 'Incorporation year', v: result.company_profile?.founded || 'Not available' },
                      { k: 'Principal headquarters', v: result.company_profile?.headquarters || 'Not available' },
                      { k: 'Estimated employees', v: result.company_profile?.employees || 'Not available' },
                    ].map((row, i) => (
                      <div key={i} className="py-2.5 flex justify-between gap-4">
                        <span className="text-ink-500">{row.k}</span>
                        <span className="text-ink-50 font-medium text-right">{row.v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="border border-border rounded-xl p-6 space-y-4">
                  <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Verified financial ratios · SEDAR+ / public disclosures
                  </h3>
                  {result.company_profile?.financial_metrics ? (
                    <div className="divide-y divide-border text-xs">
                      {Object.entries(result.company_profile.financial_metrics).map(([k, v], i) => (
                        <div key={i} className="py-2.5 flex justify-between gap-4">
                          <span className="text-ink-500 capitalize">{k.replace(/_/g, ' ')}</span>
                          <span className="text-ink-50 font-mono font-medium">{v}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-ink-500 leading-relaxed">
                      Private entity without mandatory TSX/SEDAR+ public filing obligations. Financial viability score computed from web intelligence disclosures.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* TAB 4: Mitigations & Data Gaps */}
            {activeTab === 'mitigation' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="border border-border rounded-xl p-6 space-y-4">
                  <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Recommended risk mitigations
                  </h3>
                  <ol className="space-y-0">
                    {result.recommendations?.map((rec, i) => (
                      <li key={i} className="py-2.5 border-t border-border first:border-t-0 flex items-start gap-3 text-xs">
                        <span className="font-mono text-ink-500 shrink-0">{i + 1}.</span>
                        <span className="text-ink-200 leading-relaxed">{rec}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="border border-border rounded-xl p-6 space-y-4">
                  <h3 className="text-xs font-medium text-ink-500 uppercase tracking-wider flex items-center gap-2">
                    Data gaps & verification items · Section 9.2
                  </h3>
                  <ol className="space-y-0">
                    {result.data_gaps?.map((gap, i) => (
                      <li key={i} className="py-2.5 border-t border-border first:border-t-0 flex items-start gap-3 text-xs">
                        <span className="font-mono text-tier-medium shrink-0">{i + 1}.</span>
                        <span className="text-ink-300 leading-relaxed">{gap}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}

            {/* TAB 5: Official Export Center */}
            {activeTab === 'export' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="border border-border rounded-xl p-6 space-y-4 flex flex-col justify-between">
                  <div className="space-y-2">
                    <FileText size={18} className="text-ink-400" strokeWidth={1.75} />
                    <h3 className="text-sm font-medium text-ink-50">SK-VDD-001 PDF summary report</h3>
                    <p className="text-xs text-ink-500 leading-relaxed">
                      Two-pass PDF containing document control, executive scorecard, signal attributions, gaps, and human-in-the-loop sign-off.
                    </p>
                  </div>
                  <button
                    onClick={handleDownloadPdf}
                    className="w-full py-2.5 rounded-lg bg-white hover:bg-ink-200 text-black text-xs font-medium flex items-center justify-center gap-2 transition-colors"
                  >
                    <Download size={14} />
                    Download official PDF report
                  </button>
                </div>

                <div className="border border-border rounded-xl p-6 space-y-4 flex flex-col justify-between">
                  <div className="space-y-2">
                    <Layers size={18} className="text-ink-400" strokeWidth={1.75} />
                    <h3 className="text-sm font-medium text-ink-50">Canonical JSON payload · Section 8</h3>
                    <p className="text-xs text-ink-500 leading-relaxed">
                      Machine-readable JSON schema conformant with enterprise GRC / case management ingestion contracts.
                    </p>
                  </div>
                  <button
                    onClick={handleExportJson}
                    className="w-full py-2.5 rounded-lg border border-border hover:border-border-light text-ink-200 text-xs font-medium flex items-center justify-center gap-2 transition-colors"
                  >
                    <Download size={14} />
                    Export canonical JSON payload
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-border py-6 text-center text-xs text-ink-700">
        <p>DRiskify — NIVETA Platform · Skill SK-VDD-001 · Canada vendor due diligence · Confidential</p>
      </footer>
    </div>
  );
}
