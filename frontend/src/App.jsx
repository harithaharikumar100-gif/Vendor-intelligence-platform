import React, { useState, useEffect } from 'react';
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
  const [concerns, setConcerns] = useState('');
  
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [presets, setPresets] = useState([]);
  const [normalizedPreview, setNormalizedPreview] = useState('');

  // Fetch presets and health on mount
  useEffect(() => {
    fetch('/api/presets')
      .then((res) => res.json())
      .then((data) => setPresets(data))
      .catch(() => {});

    // Initial default analysis for Shopify
    handleRunAnalysis('Shopify Inc.', 'Technology & SaaS', 'Canada', 'https://www.shopify.com', 'SHOP');
  }, []);

  // Live input normalization preview
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
      case 'Low': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
      case 'Medium': return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
      case 'High': return 'text-orange-400 bg-orange-500/10 border-orange-500/30';
      case 'Critical': return 'text-rose-400 bg-rose-500/15 border-rose-500/30';
      default: return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
    }
  };

  return (
    <div className="min-h-screen bg-background text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white">
      {/* Top Navigation */}
      <header className="border-b border-border/80 bg-surface/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500 to-sky-700 flex items-center justify-center shadow-lg shadow-sky-500/20">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-extrabold tracking-tight text-white">DRiskify</span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-400 border border-sky-500/30 font-mono">
                  SK-VDD-001
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium">NIVETA Platform • Canadian Due Diligence</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>SEDAR+ • CCCS • OSFI • Live</span>
            </div>
            <button
              onClick={() => handleRunAnalysis()}
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition-all shadow-md shadow-sky-600/20 disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Re-scan Entity
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Search & Hero Card */}
        <section className="bg-surface border border-border rounded-2xl p-6 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-sky-500/5 rounded-full blur-3xl pointer-events-none" />

          <div className="max-w-3xl space-y-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Vendor Intelligence Scraping & Risk Scoring
              </h1>
              <p className="text-sm text-slate-400 mt-1">
                Autonomous 5-dimension intelligence sweep across Canadian & International public records.
              </p>
            </div>

            {/* Search Input Box */}
            <div className="relative flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  value={vendorInput}
                  onChange={(e) => setVendorInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleRunAnalysis()}
                  placeholder="Enter Vendor Legal Name (e.g. Shopify Inc., BlackBerry Ltd., CGI Inc.)..."
                  className="w-full pl-11 pr-4 py-3 bg-slate-900/90 border border-slate-700/80 rounded-xl text-white text-sm focus:outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20 transition-all placeholder:text-slate-500"
                />
              </div>

              <button
                onClick={() => handleRunAnalysis()}
                disabled={loading}
                className="px-6 py-3 rounded-xl bg-gradient-to-r from-sky-600 to-sky-500 hover:from-sky-500 hover:to-sky-400 text-white font-bold text-sm shadow-lg shadow-sky-600/30 transition-all disabled:opacity-50 flex items-center justify-center gap-2 shrink-0"
              >
                {loading ? <RefreshCw size={16} className="animate-spin" /> : <Sparkles size={16} />}
                Execute Due Diligence
              </button>
            </div>

            {/* Normalization Suffix Strip Feedback */}
            {normalizedPreview && (
              <div className="flex items-center gap-2 text-xs text-sky-400 font-mono">
                <CheckCircle2 size={13} />
                <span>Normalised to: <strong className="text-white">{normalizedPreview}</strong> (Legal suffix stripped)</span>
              </div>
            )}

            {/* Quick Presets Chips */}
            <div className="pt-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-2">
                Quick Select:
              </span>
              <div className="inline-flex flex-wrap gap-1.5 mt-1 sm:mt-0">
                {presets.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => selectPreset(p)}
                    className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-sky-500/40 text-slate-300 hover:text-sky-300 text-xs font-medium transition-all"
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Advanced Identifiers Toggle */}
            <div className="pt-1">
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors font-medium"
              >
                <Filter size={13} />
                <span>{showAdvanced ? 'Hide' : 'Show'} Advanced Identifiers (CRA BN, TSX Ticker, Domain)</span>
              </button>

              {showAdvanced && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 p-4 bg-slate-900/60 rounded-xl border border-slate-800 text-xs">
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Industry Domain</label>
                    <input
                      type="text"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">CRA Business Number (9-digit)</label>
                    <input
                      type="text"
                      value={businessNumber}
                      onChange={(e) => setBusinessNumber(e.target.value)}
                      placeholder="e.g. 123456789"
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Stock Ticker (TSX/NYSE)</label>
                    <input
                      type="text"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value)}
                      placeholder="e.g. SHOP, BB"
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Loading Progressive State */}
        {loading && (
          <div className="bg-surface border border-sky-500/30 rounded-2xl p-8 text-center space-y-4 animate-pulse">
            <div className="w-12 h-12 rounded-2xl bg-sky-500/20 text-sky-400 mx-auto flex items-center justify-center">
              <RefreshCw size={24} className="animate-spin" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">
                Gathering Autonomous Intelligence on {vendorInput}...
              </h3>
              <p className="text-xs text-sky-400 font-mono mt-1">
                {loadingStep === 1 && '1/4 Input Normalisation & CBCA Jurisdiction Resolution...'}
                {loadingStep === 2 && '2/4 Querying SEDAR+, Tier-1 Canadian Media & CanLII...'}
                {loadingStep === 3 && '3/4 Inspecting CCCS Advisories, CISA KEV & OSFI/FINTRAC...'}
                {loadingStep >= 4 && '4/4 Applying SK-VDD-001 Signal Taxonomy & AI Synthesis...'}
              </p>
            </div>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-500/40 text-rose-300 text-sm flex items-center gap-3">
            <AlertTriangle size={18} className="shrink-0" />
            <div>
              <strong>Error:</strong> {error}
            </div>
          </div>
        )}

        {/* Analysis Results View */}
        {result && !loading && (
          <div className="space-y-8">
            {/* Automatic Escalations Banner (Section 10.1) */}
            <EscalationBanner escalations={result.automatic_escalations} />

            {/* Executive Hero Banner */}
            <div className="bg-surface border border-border rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-center justify-between gap-6">
              <div className="space-y-2 flex-1">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-2xl font-extrabold text-white tracking-tight">
                    {result.vendor_name || vendorInput}
                  </h2>
                  <span className={`px-3 py-1 rounded-full text-xs font-extrabold uppercase tracking-wider border ${getTierColor(result.overall_risk_rating)}`}>
                    {result.overall_risk_rating} Risk ({result.traffic_light})
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Jurisdiction: <strong className="text-slate-200">{result.registration_country}</strong> • Industry: <strong className="text-slate-200">{result.company_profile?.industry || industry}</strong> • Data Confidence: <strong className="text-sky-400">{result.confidence_score}%</strong> (36m Horizon)
                </p>
                <p className="text-xs text-slate-300 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  <span className="font-semibold text-slate-100">Recommended Action: </span>
                  {result.recommended_action}
                </p>
              </div>

              {/* Score Gauge */}
              <div className="shrink-0 border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-6 flex items-center justify-center">
                <GaugeMeter
                  score={result.overall_score}
                  rating={result.overall_risk_rating}
                  traffic={result.traffic_light}
                />
              </div>
            </div>

            {/* Entity Intelligence Quick Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Key size={12} className="text-purple-400" /> Executive Leadership
                </span>
                <span className="text-xs font-bold text-white mt-1.5 truncate" title={result.company_profile?.ceo}>
                  {result.company_profile?.ceo || 'Not Available'}
                </span>
              </div>

              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Building2 size={12} className="text-sky-400" /> Corporate Founder
                </span>
                <span className="text-xs font-bold text-white mt-1.5 truncate" title={result.company_profile?.founder}>
                  {result.company_profile?.founder || 'Not Available'}
                </span>
              </div>

              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Clock size={12} className="text-emerald-400" /> Incorporated
                </span>
                <span className="text-xs font-bold text-white mt-1.5">
                  {result.company_profile?.founded || 'Not Available'}
                </span>
              </div>

              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Globe size={12} className="text-amber-400" /> Headquarters
                </span>
                <span className="text-xs font-bold text-white mt-1.5 truncate" title={result.company_profile?.headquarters}>
                  {result.company_profile?.headquarters || 'Not Available'}
                </span>
              </div>

              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Users size={12} className="text-indigo-400" /> Est. Employees
                </span>
                <span className="text-xs font-bold text-white mt-1.5">
                  {result.company_profile?.employees ? `${result.company_profile.employees}` : 'Not Available'}
                </span>
              </div>

              <div className="bg-surface p-3.5 rounded-xl border border-border flex flex-col justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <TrendingUp size={12} className="text-emerald-400" /> Annual Revenue
                </span>
                <span className="text-xs font-bold font-mono text-emerald-400 mt-1.5 truncate">
                  {result.company_profile?.financial_metrics?.revenue || 'Private / Unlisted'}
                </span>
              </div>
            </div>

            {/* 5-Dimension Mini Cards Grid (Section 7.2) */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                { key: 'financial', label: 'Financial Viability', wt: '30%', icon: TrendingUp, color: 'text-emerald-400', border: 'border-emerald-500/30' },
                { key: 'reputation', label: 'Reputational Risk', wt: '20%', icon: Globe, color: 'text-sky-400', border: 'border-sky-500/30' },
                { key: 'key_person', label: 'Key-Person & Gov', wt: '20%', icon: Key, color: 'text-purple-400', border: 'border-purple-500/30' },
                { key: 'cyber', label: 'Technology & Cyber', wt: '20%', icon: Cpu, color: 'text-amber-400', border: 'border-amber-500/30' },
                { key: 'compliance', label: 'Regulatory Compliance', wt: '10%', icon: Scale, color: 'text-rose-400', border: 'border-rose-500/30' },
              ].map((dim) => {
                const s = result.risk_scores?.[dim.key] ?? 20;
                const Icon = dim.icon;
                return (
                  <div key={dim.key} className={`bg-surface p-4 rounded-xl border ${dim.border} shadow-lg relative overflow-hidden`}>
                    <div className="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider mb-2">
                      <span>{dim.label}</span>
                      <span className="text-[10px] text-slate-500">({dim.wt})</span>
                    </div>
                    <div className="flex items-baseline justify-between">
                      <span className={`text-2xl font-extrabold font-mono ${dim.color}`}>{s}</span>
                      <span className="text-[11px] text-slate-500 font-mono">/100</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Tab Navigation */}
            <div className="border-b border-border flex items-center gap-2 overflow-x-auto">
              {[
                { id: 'overview', label: 'Executive Overview', icon: Layers },
                { id: 'dimensions', label: '5 Risk Dimensions', icon: Shield },
                { id: 'corporate', label: 'Corporate Registry & Filings', icon: Building2 },
                { id: 'mitigation', label: 'Mitigations & Data Gaps', icon: ListChecks },
                { id: 'export', label: 'Official Export Center', icon: Download },
              ].map((t) => {
                const Icon = t.icon;
                const active = activeTab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all whitespace-nowrap ${
                      active
                        ? 'border-sky-500 text-sky-400 bg-sky-500/5'
                        : 'border-transparent text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Icon size={14} />
                    {t.label}
                  </button>
                );
              })}
            </div>

            {/* TAB 1: Executive Overview */}
            {activeTab === 'overview' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-6 bg-surface p-6 rounded-2xl border border-border">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Shield size={16} className="text-sky-400" />
                    5-Dimension Risk Radar
                  </h3>
                  <RadarChart scores={result.risk_scores} />
                </div>

                <div className="lg:col-span-6 space-y-4">
                  <div className="bg-surface p-6 rounded-2xl border border-border space-y-3">
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                      Holistic Analyst Assessment (Section 8)
                    </h3>
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {result.analyst_notes}
                    </p>
                  </div>

                  <div className="bg-surface p-6 rounded-2xl border border-border space-y-3">
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                      Authoritative Sources Ingested (Section 5)
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {result.data_sources_used?.map((src, i) => (
                        <span key={i} className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-400">
                          ✓ {src}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: 5 Risk Dimensions */}
            {activeTab === 'dimensions' && (
              <div className="space-y-4">
                <DimensionCard
                  title="Financial Viability Risk"
                  weight="30% Weight"
                  score={result.risk_scores?.financial ?? 20}
                  sources="SEDAR+ Filings, CBCA Registry, Solvency, Liquidity Ratios"
                  summary={result.explanations?.financial?.summary}
                  signals={result.explanations?.financial?.signals}
                  links={result.evidence_links?.financial}
                  colorHex="#10b981"
                />

                <DimensionCard
                  title="Reputational Risk"
                  weight="20% Weight"
                  score={result.risk_scores?.reputation ?? 20}
                  sources="CBC, Globe and Mail, Financial Post, CanLII Litigation (36m)"
                  summary={result.explanations?.reputation?.summary}
                  articles={result.explanations?.reputation?.articles}
                  links={result.evidence_links?.reputation}
                  colorHex="#38bdf8"
                />

                <DimensionCard
                  title="Key-Person & Governance Risk"
                  weight="20% Weight"
                  score={result.risk_scores?.key_person ?? 20}
                  sources="SEDI Insiders, LinkedIn, OFAC/OSFI Sanctions Lists, CanLII"
                  summary={result.explanations?.key_person?.summary}
                  persons={result.explanations?.key_person?.persons}
                  links={result.evidence_links?.key_person}
                  colorHex="#c084fc"
                />

                <DimensionCard
                  title="Technology & Cybersecurity Risk"
                  weight="20% Weight"
                  score={result.risk_scores?.cyber ?? 20}
                  sources="CCCS (cyber.gc.ca), CISA KEV, NVD (CVSS >= 7.0), HIBP"
                  summary={result.explanations?.cyber?.summary}
                  signals={result.explanations?.cyber?.signals}
                  links={result.evidence_links?.cyber}
                  colorHex="#f59e0b"
                />

                <DimensionCard
                  title="Regulatory Compliance Risk"
                  weight="10% Weight"
                  score={result.risk_scores?.compliance ?? 20}
                  sources="OSFI Enforcement, FINTRAC AMPs, CSA Orders, OPC PIPEDA, CRTC"
                  summary={result.explanations?.compliance?.summary}
                  signals={result.explanations?.compliance?.signals}
                  links={result.evidence_links?.compliance}
                  colorHex="#f43f5e"
                />
              </div>
            )}

            {/* TAB 3: Corporate Registry & Filings */}
            {activeTab === 'corporate' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Building2 size={16} className="text-sky-400" />
                    Corporate Entity Verification
                  </h3>
                  <div className="divide-y divide-border text-xs">
                    {[
                      { k: 'Legal Entity Name', v: result.vendor_name },
                      { k: 'Jurisdiction', v: result.registration_country },
                      { k: 'CRA Business Number', v: result.business_number || 'Inferred via Registry' },
                      { k: 'Executive Leadership (CEO)', v: result.company_profile?.ceo || 'Not Available' },
                      { k: 'Corporate Founder', v: result.company_profile?.founder || 'Not Available' },
                      { k: 'Incorporation Year', v: result.company_profile?.founded || 'Not Available' },
                      { k: 'Principal Headquarters', v: result.company_profile?.headquarters || 'Not Available' },
                      { k: 'Estimated Employees', v: result.company_profile?.employees || 'Not Available' },
                    ].map((row, i) => (
                      <div key={i} className="py-2.5 flex justify-between">
                        <span className="text-slate-400 font-medium">{row.k}</span>
                        <span className="text-white font-bold">{row.v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <TrendingUp size={16} className="text-emerald-400" />
                    Verified Financial Ratios (SEDAR+ / Public Disclosures)
                  </h3>
                  {result.company_profile?.financial_metrics ? (
                    <div className="divide-y divide-border text-xs">
                      {Object.entries(result.company_profile.financial_metrics).map(([k, v], i) => (
                        <div key={i} className="py-2.5 flex justify-between">
                          <span className="text-slate-400 font-medium capitalize">{k.replace(/_/g, ' ')}</span>
                          <span className="text-emerald-400 font-mono font-bold">{v}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Private entity without mandatory TSX/SEDAR+ public filing obligations. Financial viability score computed from web intelligence disclosures.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* TAB 4: Mitigations & Data Gaps */}
            {activeTab === 'mitigation' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <CheckCircle2 size={16} className="text-sky-400" />
                    Recommended Risk Mitigations
                  </h3>
                  <div className="space-y-2.5">
                    {result.recommendations?.map((rec, i) => (
                      <div key={i} className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 flex items-start gap-3 text-xs">
                        <span className="w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center font-bold shrink-0">
                          {i + 1}
                        </span>
                        <span className="text-slate-200 leading-relaxed">{rec}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <AlertTriangle size={16} className="text-amber-400" />
                    Data Gaps & Verification Items (Section 9.2)
                  </h3>
                  <div className="space-y-2.5">
                    {result.data_gaps?.map((gap, i) => (
                      <div key={i} className="p-3 bg-amber-500/5 rounded-xl border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-200/90">
                        <span className="font-mono text-amber-400 font-bold">[ ]</span>
                        <span className="leading-relaxed">{gap}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: Official Export Center */}
            {activeTab === 'export' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="w-10 h-10 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center">
                      <FileText size={20} />
                    </div>
                    <h3 className="text-base font-bold text-white">SK-VDD-001 PDF Summary Report</h3>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Two-pass PDF containing Document Control, Executive Scorecard, Signal Attributions, Gaps, and Human-in-the-Loop Sign-off.
                    </p>
                  </div>
                  <button
                    onClick={handleDownloadPdf}
                    className="w-full py-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-sky-600/20"
                  >
                    <Download size={15} />
                    Download Official PDF Report
                  </button>
                </div>

                <div className="bg-surface p-6 rounded-2xl border border-border space-y-4 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
                      <Layers size={20} />
                    </div>
                    <h3 className="text-base font-bold text-white">Canonical JSON Payload (Section 8)</h3>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Machine-readable JSON schema conformant with enterprise GRC / Case Management ingestion contracts.
                    </p>
                  </div>
                  <button
                    onClick={handleExportJson}
                    className="w-full py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-bold flex items-center justify-center gap-2 transition-all"
                  >
                    <Download size={15} />
                    Export Canonical JSON Payload
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Minimal Footer */}
      <footer className="border-t border-border/60 py-6 text-center text-xs text-slate-500">
        <p>DRiskify — NIVETA Platform • Skill SK-VDD-001 • Canada Vendor Due Diligence • Confidential</p>
      </footer>
    </div>
  );
}
