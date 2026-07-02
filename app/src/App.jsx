import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

// v3 flow components
import HeroVerdict from './features/stock/HeroVerdict'
import MarketBetPanel from './features/stock/MarketBetPanel'
import ScenariosWithSliders from './features/stock/ScenariosWithSliders'
import WhatYouNeedToBelieve from './features/stock/WhatYouNeedToBelieve'
import MultiplesCheck from './features/stock/MultiplesCheck'
import CalibrationPanel from './features/stock/CalibrationPanel'
import ModelQualityPanel from './features/stock/ModelQualityPanel'
import Conclusion from './features/stock/Conclusion'
import Glossary from './shared/Glossary'
import LearnMore from './shared/LearnMore'
import DisclosureSection from './shared/DisclosureSection'

// retained components (well-tested)
import SearchBar from './shared/SearchBar'
import LoadingState from './shared/LoadingState'
import FCFHistoryChart from './features/stock/FCFHistoryChart'
import SensitivityTable from './features/stock/SensitivityTable'
import WACCBreakdown from './features/stock/WACCBreakdown'
import EPFLCitation from './shared/EPFLCitation'
import DiversificationLab from './features/portfolio/DiversificationLab'
import NowOrLaterLab from './features/money/NowOrLaterLab'
import API from './shared/api'

function getInitialTicker() {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get('ticker')?.trim().toUpperCase() || ''
}

function getAnalysisError(e) {
  const detail = e.response?.data?.detail
  const apiMessage = (typeof detail === 'object' ? detail?.error : detail)
    || e.response?.data?.error

  if (apiMessage) return apiMessage

  if (e.code === 'ERR_NETWORK') {
    return [
      'The analysis API is not reachable.',
      `Start the backend on ${API} or check the frontend API URL.`,
    ].join(' ')
  }

  if (e.response?.status >= 500) {
    return 'The analysis API returned a server error. Retry once, then check backend logs.'
  }

  return 'Analysis failed. Please try again.'
}

export default function App() {
  const initialTicker = getInitialTicker()
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [data, setData]           = useState(null)
  const [activeTicker, setActive] = useState(initialTicker)
  const [glossaryOpen, setGlossaryOpen] = useState(false)
  const [view, setView] = useState('money')

  const analyse = useCallback(async (ticker, { syncUrl = true } = {}) => {
    const normalizedTicker = ticker.trim().toUpperCase()
    if (!normalizedTicker) return

    if (syncUrl) {
      const url = new URL(window.location.href)
      url.searchParams.set('ticker', normalizedTicker)
      window.history.replaceState({}, '', url)
    }

    setLoading(true)
    setError(null)
    setData(null)
    setActive(normalizedTicker)
    try {
      const res = await axios.post(`${API}/analyse`, {
        ticker: normalizedTicker,
        risk_free_rate: 0.045,
        market_risk_premium: 0.055,
        terminal_growth: 0.025,
      })
      setData(res.data)
    } catch (e) {
      setError(getAnalysisError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!initialTicker) return undefined

    const id = window.setTimeout(() => {
      analyse(initialTicker, { syncUrl: false })
    }, 0)

    return () => window.clearTimeout(id)
  }, [analyse, initialTicker])

  const d = data

  return (
    <div className="app-shell">
      {/* Topbar */}
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand-mark">
            <span>OpenQuant</span>
            <span className="brand-dot" />
          </div>
          <div className="topbar-subtitle">
            Finance theory applied to live US market data.
          </div>
          <div style={{ display: 'flex', gap: 4, marginLeft: 16 }}>
            <button
              onClick={() => setView('money')}
              className="topbar-action"
              style={{ fontWeight: view === 'money' ? 700 : 400, opacity: view === 'money' ? 1 : 0.55 }}
            >
              Money
            </button>
            <button
              onClick={() => setView('stock')}
              className="topbar-action"
              style={{ fontWeight: view === 'stock' ? 700 : 400, opacity: view === 'stock' ? 1 : 0.55 }}
            >
              Stock
            </button>
            <button
              onClick={() => setView('portfolio')}
              className="topbar-action"
              style={{ fontWeight: view === 'portfolio' ? 700 : 400, opacity: view === 'portfolio' ? 1 : 0.55 }}
            >
              Portfolio
            </button>
          </div>
          <button
            onClick={() => setGlossaryOpen(true)}
            aria-label="Open glossary"
            className="topbar-action"
          >
            📖 Glossary
          </button>
          <a href="https://github.com/A-bv/openquant" target="_blank" rel="noreferrer"
            className="topbar-link">
            GitHub ↗
          </a>
        </div>
      </header>

      {/* Glossary drawer */}
      <Glossary open={glossaryOpen} onClose={() => setGlossaryOpen(false)} />

      <main className="page">

        {view === 'money' && <NowOrLaterLab API={API} />}

        {view === 'portfolio' && <DiversificationLab API={API} />}

        {view === 'stock' && (
        <>

        {/* Search */}
        <section className={`card ${d ? 'analysis-toolbar' : 'intro-card'}`}>
          {!d && (
            <>
              <div className="eyebrow">
                Live Corporate Finance Lab
              </div>
              <h1 className="page-title">
                What Does a Stock Price Tell You?
              </h1>
              <p className="page-copy">
                OpenQuant uses real market data and EPFL finance formulas to
                estimate the cash-flow growth required to justify today's price,
                then backtests whether similar past conclusions were informative.
              </p>
              <p className="intro-proof">
                Real US market data · EPFL course formulas · Historical backtests
              </p>
            </>
          )}
          <div className={d ? 'toolbar-grid' : undefined}>
            {d && (
              <div>
                <div className="eyebrow">
                  EPFL Finance Lab
                </div>
                <div className="toolbar-title">
                  Ticker converted into a finance case
                </div>
              </div>
            )}
            <SearchBar
              key={activeTicker || 'empty-search'}
              onAnalyse={analyse}
              loading={loading}
              data={d}
              value={activeTicker}
              showSummary={false}
            />
          </div>
        </section>

        {/* Error */}
        {error && (
          <div style={{
            background: '#FCEBEB', border: '0.5px solid #F5B5B5',
            borderRadius: 8, padding: '14px 18px',
            color: '#A32D2D', fontSize: 13,
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <span>{error}</span>
            <button onClick={() => analyse(activeTicker)} style={{
              color: '#185FA5', background: 'none', border: 'none',
              cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
            }}>
              Retry ↺
            </button>
          </div>
        )}

        {loading && <LoadingState ticker={activeTicker} />}

        {/* Not-suitable analysis */}
        {d && !d.is_suitable && (
          <section style={{
            background: '#FCEBEB', border: '0.5px solid #F5B5B5',
            borderRadius: 12, padding: '24px 28px',
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#A32D2D', marginBottom: 10 }}>
              🔴 DCF not suitable for {d.company_name}
            </div>
            <p style={{ fontSize: 13, color: '#374151', marginBottom: 14, lineHeight: 1.6 }}>
              {d.suitability_message}
            </p>
            {d.alternative_methods?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#111827', marginBottom: 6 }}>Consider instead:</div>
                {d.alternative_methods.map(m => (
                  <div key={m} style={{ fontSize: 12, color: '#6B7280', padding: '2px 0' }}>· {m}</div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Main results — v3 flow */}
        {d && d.is_suitable && (
          <>
            <HeroVerdict d={d} />

            <ScenariosWithSliders key={d.ticker} d={d} />
            <WhatYouNeedToBelieve d={d} />

            <DisclosureSection
              eyebrow="Reverse DCF detail"
              title="Compare implied growth with the company's history"
              summary="Open this to see the full reverse DCF comparison against historical median, mean, revenue CAGR, and GDP."
            >
              <MarketBetPanel d={d} />
            </DisclosureSection>

            <DisclosureSection
              eyebrow="Model reliability"
              title="How much should you trust this analysis?"
              summary="The formula can be correct while the stock-return signal remains weak. Open this before treating any model value as a forecast."
            >
              <CalibrationPanel placement="hero" />
              <div style={{ marginTop: 12 }}>
                <ModelQualityPanel d={d} />
              </div>
            </DisclosureSection>

            <DisclosureSection
              eyebrow="Cross-check"
              title="Check the model output against market multiples"
              summary="P/E, EV/EBITDA, and FCF yield provide a quick sanity check, separate from the DCF."
            >
              <MultiplesCheck d={d} />
            </DisclosureSection>

            {/* FCF history — kept as a focused section */}
            <DisclosureSection
              eyebrow="Cash-flow evidence"
              title="Inspect free cash flow history"
              summary="Use this to judge whether the growth assumption is grounded in what the business has actually produced."
            >
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
                Free cash flow history
                <EPFLCitation source="Berk-DeMarzo Ch.7 · FCF formula" test="test_epfl_exam1.py::TestExam1Problem2_FCF" />
                <LearnMore section="fcfHistory" />
              </h3>
              <p style={{ fontSize: 12, color: '#6B7280', marginBottom: 12 }}>
                What the business actually generated. Red bars = negative FCF.
              </p>
              <FCFHistoryChart history={d.fcf.history} companyName={d.company_name} />
            </DisclosureSection>

            {/* Sensitivity */}
            <DisclosureSection
              eyebrow="Sensitivity"
              title="Open the valuation heatmap"
              summary="See how quickly the conclusion changes when growth and discount rate move together."
            >
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
                Sensitivity heatmap
                <LearnMore section="sensitivity" />
              </h3>
              <p style={{ fontSize: 12, color: '#6B7280', marginBottom: 12, lineHeight: 1.5 }}>
                Each cell shows what the model says the stock is worth, at that combination of growth rate (rows) and discount rate (columns).
                <br />
                <strong>Read this:</strong> <span style={{ color: '#3B6D11' }}>green = above today's price</span> · <span style={{ color: '#A32D2D' }}>red = below today's price</span> · amber border = closest match to today's price.
              </p>
              <SensitivityTable sensitivity={d.sensitivity} currentPrice={d.current_price} />
            </DisclosureSection>

            {/* WACC breakdown — the math */}
            <DisclosureSection
              eyebrow="Course formula"
              title="Show the WACC calculation"
              summary="Open the CAPM and WACC machinery when you want to audit the discount rate."
            >
              <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
                Show your work — discount rate (WACC)
                <EPFLCitation source="Berk-DeMarzo Ch.12 (CAPM), Ch.15 (WACC)" />
                <LearnMore section="wacc" />
              </h3>
              <p style={{ fontSize: 12, color: '#6B7280', marginBottom: 12 }}>
                Every component of the discount rate, sourced and explained.
              </p>
              <WACCBreakdown wacc={d.wacc} />
            </DisclosureSection>

            {/* Per-stock conclusion + take-aways + next actions */}
            <Conclusion d={d} onAnalyse={analyse} />

            {/* Buffett footer */}
            <DisclosureSection
              eyebrow="Methodology note"
              title="Why this uses textbook DCF rather than Buffett owner earnings"
              summary="Different valuation philosophies can produce different answers. This app uses Berk-DeMarzo because the formulas are traceable and testable."
            >
              <div style={{
                fontSize: 12,
                color: '#6B7280',
                lineHeight: 1.65,
                maxWidth: 760,
              }}>
                <strong style={{ color: '#374151' }}>Note on methodology.</strong>{' '}
                Buffett doesn't use WACC — he discounts at the long-bond yield (~5%), uses
                "owner's earnings" instead of FCF, and demands a 30%+ margin of safety. His
                method gives different (often higher) IVs but he'd refuse to apply it to many
                of these companies. We use the textbook method (Berk-DeMarzo) because every
                step is traceable to a chapter and verifiable against the textbook's worked
                problems. Both philosophies are legitimate.
              </div>
            </DisclosureSection>

            {/* Brand footer */}
            <div style={{
              textAlign: 'center', fontSize: 11, color: '#9CA3AF',
              padding: '12px 0', letterSpacing: '0.04em',
            }}>
              <strong style={{ color: '#6B7280' }}>OpenQuant</strong> · Theory. Reality. You decide.
            </div>
          </>
        )}

        </>
        )}
      </main>
    </div>
  )
}
