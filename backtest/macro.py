"""
Period-appropriate macro inputs for the historical backtest.

Using 2024 macro inputs for a 2014 valuation would be retroactive cheating
(low rates make everything look cheap with the benefit of hindsight). For each
"as of" date, we hard-code the inputs that were observable then.

Sources:
  - Risk-free rate: FRED `DGS10` (10-year US Treasury constant maturity), spot value
  - Market risk premium: Damodaran "Implied ERP" monthly series
  - Terminal growth: held at 2.5% across all periods (long-run nominal GDP)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MacroSnapshot:
    """Macro inputs for a single point in time."""
    as_of: date
    risk_free_rate: float
    market_risk_premium: float
    terminal_growth: float


# Hand-curated snapshots — extend as backtest grows.
# Source notes inline.
SNAPSHOTS: list[MacroSnapshot] = [
    # Jan 31, 2014 — the primary backtest date
    MacroSnapshot(
        as_of=date(2014, 1, 31),
        risk_free_rate=0.0265,   # FRED DGS10 Jan 31, 2014 = 2.65%
        market_risk_premium=0.0500,  # Damodaran implied ERP Jan 2014 ≈ 5.00%
        terminal_growth=0.025,
    ),
    # Earlier reference points for robustness (optional secondary backtests)
    MacroSnapshot(
        as_of=date(2010, 1, 29),
        risk_free_rate=0.0364,   # FRED DGS10 Jan 29, 2010 = 3.64%
        market_risk_premium=0.0451,  # Damodaran implied ERP Jan 2010 ≈ 4.51%
        terminal_growth=0.025,
    ),
    MacroSnapshot(
        as_of=date(2018, 1, 31),
        risk_free_rate=0.0270,   # FRED DGS10 Jan 31, 2018 = 2.70%
        market_risk_premium=0.0508,  # Damodaran implied ERP Jan 2018 ≈ 5.08%
        terminal_growth=0.025,
    ),
    # Today's default — for cross-checking the live model
    MacroSnapshot(
        as_of=date(2024, 1, 31),
        risk_free_rate=0.0415,   # FRED DGS10 Jan 31, 2024 = 4.15%
        market_risk_premium=0.0480,  # Damodaran implied ERP Jan 2024 ≈ 4.80%
        terminal_growth=0.025,
    ),
]


def get_macro(as_of: date) -> MacroSnapshot:
    """
    Return the macro snapshot at or just before the given date.

    Raises:
        ValueError: If no snapshot exists for or before the given date.
    """
    eligible = [s for s in SNAPSHOTS if s.as_of <= as_of]
    if not eligible:
        raise ValueError(
            f"No macro snapshot available on or before {as_of}. "
            f"Earliest snapshot: {min(s.as_of for s in SNAPSHOTS)}."
        )
    return max(eligible, key=lambda s: s.as_of)


if __name__ == "__main__":
    test_dates = [date(2014, 1, 31), date(2014, 6, 30), date(2010, 1, 29)]
    for d in test_dates:
        m = get_macro(d)
        print(f"{d}: rf={m.risk_free_rate:.2%}, MRP={m.market_risk_premium:.2%}, gT={m.terminal_growth:.2%}")
