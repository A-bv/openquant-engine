"""
OpenQuant — Central configuration.
All constants live here. No magic numbers anywhere in the codebase.
"""

# ── Project identity ──────────────────────────────────────────────────────────
PROJECT_NAME = "OpenQuant"
PROJECT_TAGLINE = (
    "OpenQuant does not tell you what a company is worth. "
    "It tells you what assumptions are required for the current price to make sense."
)
PROJECT_VERSION = "1.0.0"

# ── Data sources ──────────────────────────────────────────────────────────────
EDGAR_BASE_URL = "https://data.sec.gov"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

CACHE_DIR = "data/cache"
CACHE_TTL_RECENT_SECONDS = 86_400        # 24h for recent data
CACHE_TTL_HISTORICAL_SECONDS = None      # permanent for historical

# ── Market defaults ───────────────────────────────────────────────────────────
DEFAULT_RISK_FREE_RATE = 0.045           # 10Y US Treasury — update periodically
DEFAULT_MARKET_RISK_PREMIUM = 0.055      # Damodaran estimate
DEFAULT_MARKET_INDEX = "^GSPC"           # S&P 500
DEFAULT_TERMINAL_GROWTH_RATE = 0.025     # Long-run nominal GDP growth
MAX_TERMINAL_GROWTH_RATE = 0.03          # Hard cap — cannot exceed nominal GDP
TERMINAL_GROWTH_MATURE_WARNING = 0.025   # Warn above this for mature companies
DEFAULT_TRADING_DAYS = 252               # Trading days per year

# ── DCF defaults ──────────────────────────────────────────────────────────────
FORECAST_HORIZON_YEARS = 10
SCENARIO_CONSERVATIVE_GROWTH_MULT = 0.7
SCENARIO_OPTIMISTIC_GROWTH_MULT = 1.3
SCENARIO_CONSERVATIVE_WACC_ADD = 0.01
SCENARIO_OPTIMISTIC_WACC_SUB = 0.01
TERMINAL_VALUE_WARNING_THRESHOLD = 0.70  # Warn if TV > 70% of EV
TERMINAL_VALUE_SEVERE_THRESHOLD = 0.75   # Red flag if TV > 75% of EV
GROWTH_WINSOR_LOW = 0.05                 # 5th percentile
GROWTH_WINSOR_HIGH = 0.95                # 95th percentile

# ── Beta computation ──────────────────────────────────────────────────────────
BETA_LOOKBACK_YEARS = 5
BETA_ROLLING_WINDOW_DAYS = 90
BETA_RETURN_FREQUENCY = "daily"
BETA_CONFIDENCE_LEVEL = 0.95
BETA_RANGE_SEVERE_THRESHOLD = 1.0        # Rolling range > 1.0 = severe
BETA_RANGE_MILD_THRESHOLD = 0.5          # Rolling range > 0.5 = mild

# ── Suitability checks ────────────────────────────────────────────────────────
MIN_FCF_HISTORY_YEARS = 3
MIN_PRICE_HISTORY_YEARS = 2
MIN_TRADING_DAYS = 252
FCF_MARGIN_SD_SEVERE = 0.30              # SD of FCF margin > 30% = severe
FCF_MARGIN_SD_MILD = 0.15               # SD of FCF margin > 15% = mild
REVENUE_SWING_SEVERE = 0.30             # Peak-to-trough > 30% = severe
REVENUE_SWING_MILD = 0.15              # Peak-to-trough > 15% = mild
EXCLUDED_SECTORS = [                     # DCF not appropriate
    "Financial Services",
    "Banks",
    "Insurance",
    "Capital Markets",
    "Petroleum Refining",
    "Oil and Gas Extraction",
    "Crude Petroleum and Natural Gas",
    "Mining",
    "Coal Mining",
    "Metal Mining",
]

# ── Assumption Diagnostic ─────────────────────────────────────────────────────
DIAGNOSTIC_GREEN_MAX = 1     # 0-1 total severity = Green
DIAGNOSTIC_AMBER_MAX = 3     # 2-3 total severity = Amber
# 4+ = Red

# Severity weights
SEVERITY_NONE = 0
SEVERITY_MILD = 1
SEVERITY_SEVERE = 2

# Growth reasonableness
GROWTH_SEVERE_MULT = 2.0     # Implied > 2x historical CAGR = severe
GROWTH_MILD_MULT = 1.5       # Implied > 1.5x historical CAGR = mild
ASSET_LIGHT_CAPEX_THRESHOLD = 0.05  # capex/revenue < 5% = asset-light note

# ── Portfolio ─────────────────────────────────────────────────────────────────
MIN_PORTFOLIO_ASSETS = 2
MAX_PORTFOLIO_ASSETS = 10
LEDOIT_WOLF_THRESHOLD = 6    # Use Ledoit-Wolf for 6+ assets
BOOTSTRAP_RESAMPLES = 1_000
MONTE_CARLO_PORTFOLIOS = 10_000

# ── Cross-validation ──────────────────────────────────────────────────────────
CROSS_VALIDATION_TOLERANCE = 0.10  # Flag if sources diverge > 10%
CROSS_VALIDATION_FIELDS = [
    "free_cash_flow",
    "total_debt",
    "shares_outstanding",
]

# ── Multiples ─────────────────────────────────────────────────────────────────
MULTIPLES_TO_SHOW = ["EV/EBITDA", "P/E", "FCF_yield", "EV/Sales"]

# ── UI ────────────────────────────────────────────────────────────────────────
APP_TITLE = "OpenQuant"
APP_ICON = "📊"
DEFAULT_FORMULA_TOGGLE = False   # Formulas hidden by default

# ── EPFL exam fixtures — used as test ground truth ────────────────────────────
EPFL_EXAM1_FCF = [-24_000, 8_400, 9_150, 11_100, 14_850]  # thousands
EPFL_EXAM1_UNLEVERED_BETA = 1.50
EPFL_EXAM1_RF = 0.08
EPFL_EXAM1_MARKET_PREMIUM = 0.08
EPFL_EXAM1_REQUIRED_RETURN = 0.20   # 8% + 1.50 × 8% = 20%
EPFL_EXAM1_TAX_RATE = 0.35
EPFL_EXAM1_PVTS = 876_641

EPFL_H2_MEAN_RETURN = 0.10
EPFL_H2_SD = 0.1342
EPFL_H2_PORTFOLIO_SD = 0.050794  # at w = [0, 0.5, 0.5]
EPFL_H2_CORR_01 = 0.6200
EPFL_H2_CORR_02 = -0.9233
EPFL_H2_CORR_12 = -0.7133
