"""
50-stock backtest universe — S&P 500 names that existed in January 2014.

Balanced across:
  - Sector (8 sectors)
  - Size (mix of mega, large, mid)
  - Growth profile (mix of growth and value)

Selected to:
  - Test DCF on real survival outcomes (not survivorship-corrected to today's S&P)
  - Cover sectors where DCF works well (consumer, tech) AND where it doesn't (cyclical, financial)
  - Include known failure modes for the model: AMZN (negative FCF history),
    GE (long decline), BA (737 MAX), WFC (fraud scandal), XOM (oil cycles)
"""

from __future__ import annotations

# Each entry: (ticker, sector, "2014 profile") for documentation only
BACKTEST_UNIVERSE = [
    # Tech (10)
    ("AAPL",  "Tech",      "Mature giant; FCF machine"),
    ("MSFT",  "Tech",      "Mature; pre-Azure transition"),
    ("GOOGL", "Tech",      "Search monopoly; growth slowing"),
    ("CSCO",  "Tech",      "Networking incumbent; value stock"),
    ("ORCL",  "Tech",      "Pre-cloud Oracle; software giant"),
    ("INTC",  "Tech",      "Pre-foundry-decline; dominant"),
    ("IBM",   "Tech",      "Legacy IT; in slow decline"),
    ("QCOM",  "Tech",      "Mobile chip leader"),
    ("ADBE",  "Tech",      "Creative Cloud transition"),
    ("TXN",   "Tech",      "Analog chips; mature"),

    # Healthcare (7)
    ("JNJ",   "Health",    "Pharma + consumer; mature"),
    ("PFE",   "Health",    "Big pharma; patent-cliff era"),
    ("UNH",   "Health",    "Health insurance; ACA-era growth"),
    ("MRK",   "Health",    "Big pharma; pre-Keytruda explosion"),
    ("AMGN",  "Health",    "Biotech; mature"),
    ("GILD",  "Health",    "Hepatitis-C boom in 2014"),
    ("ABT",   "Health",    "Diversified medical"),

    # Financials (7) — DCF is less standard for banks; included to test suitability gating
    ("JPM",   "Financial", "Big bank; post-crisis recovery"),
    ("BAC",   "Financial", "Big bank; mortgage settlement era"),
    ("WFC",   "Financial", "Big bank; pre-fraud-scandal"),
    ("GS",    "Financial", "Investment bank"),
    ("AXP",   "Financial", "Cards; consumer credit"),
    ("SCHW",  "Financial", "Brokerage; pre-rate-hike boom"),
    ("BLK",   "Financial", "Asset manager; ETF growth"),

    # Consumer Discretionary (7)
    ("AMZN",  "Cons.Disc", "Negative-FCF growth story"),
    ("HD",    "Cons.Disc", "Home improvement; cyclical"),
    ("DIS",   "Cons.Disc", "Media; pre-streaming-pivot"),
    ("MCD",   "Cons.Disc", "Fast food; mature"),
    ("NKE",   "Cons.Disc", "Apparel; global growth"),
    ("SBUX",  "Cons.Disc", "Coffee; growth"),
    ("TJX",   "Cons.Disc", "Discount retail"),

    # Consumer Staples (5)
    ("PG",    "Staples",   "Mega-staples"),
    ("KO",    "Staples",   "Beverages; mature"),
    ("PEP",   "Staples",   "Beverages + snacks"),
    ("WMT",   "Staples",   "Retail; pre-e-commerce push"),
    ("COST",  "Staples",   "Warehouse club; growth"),

    # Industrials (6)
    ("GE",    "Industrial","Pre-decline; ICONIC failure mode case"),
    ("BA",    "Industrial","Aerospace; pre-737 MAX"),
    ("CAT",   "Industrial","Heavy equipment; cyclical"),
    ("UPS",   "Industrial","Logistics"),
    ("MMM",   "Industrial","Diversified industrial; healthcare exposure"),
    ("HON",   "Industrial","Aerospace + industrial"),

    # Energy (4)
    ("XOM",   "Energy",    "Oil major; tested through 2014-2016 oil crash"),
    ("CVX",   "Energy",    "Oil major"),
    ("COP",   "Energy",    "E&P; pure-play"),
    ("SLB",   "Energy",    "Oilfield services"),

    # Utilities (3)
    ("NEE",   "Utility",   "Renewables-leaning utility"),
    ("DUK",   "Utility",   "Regulated utility"),
    ("SO",    "Utility",   "Regulated utility; coal-heavy in 2014"),

    # Telecom (1) — small bucket
    ("VZ",    "Telecom",   "Wireless; mature"),
]

# Sanity: 50 names
assert len(BACKTEST_UNIVERSE) == 50, f"Expected 50, got {len(BACKTEST_UNIVERSE)}"

TICKERS = [t for t, _, _ in BACKTEST_UNIVERSE]
SECTORS = sorted({s for _, s, _ in BACKTEST_UNIVERSE})


def by_sector() -> dict[str, list[str]]:
    """Group tickers by sector for reporting."""
    out: dict[str, list[str]] = {}
    for t, sector, _ in BACKTEST_UNIVERSE:
        out.setdefault(sector, []).append(t)
    return out


if __name__ == "__main__":
    print(f"Universe: {len(TICKERS)} tickers, {len(SECTORS)} sectors")
    for sector, names in sorted(by_sector().items()):
        print(f"  {sector:10s} ({len(names)}): {', '.join(names)}")
