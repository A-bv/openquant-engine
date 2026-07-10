"""
OpenQuant — Sensitivity analysis for DCF valuation.

Generates two tables:
1. Implied share price across FCF growth rate × WACC grid
2. Terminal value sensitivity across terminal growth × WACC grid

The sensitivity table is the most important output for honesty —
it shows the user exactly what assumptions are needed to justify
the current price, and how sensitive the valuation is to changes.

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from openquant.config import DEFAULT_TERMINAL_GROWTH_RATE
from openquant.valuation.dcf import DCFEngine
from openquant.valuation.fcf import FCFAnalysis
from openquant.valuation.wacc import WACCResult


@dataclass
class SensitivityTable:
    """
    Sensitivity table: implied share price across two dimensions.

    Used for both:
    - Growth rate × WACC → implied share price
    - Terminal growth × WACC → implied share price
    """
    row_label: str               # e.g. "FCF Growth Rate"
    col_label: str               # e.g. "WACC"
    row_values: list[float]
    col_values: list[float]
    table: pd.DataFrame          # Index=row_values, Columns=col_values
    current_price: float         # For highlighting in UI

    def highlight_current_price(self, tolerance: float = 0.05) -> pd.DataFrame:
        """
        Return boolean DataFrame marking cells within tolerance of current price.
        Used by UI to highlight the row/col closest to current market price.
        """
        return (self.table - self.current_price).abs() / self.current_price < tolerance


class SensitivityAnalyser:
    """
    Builds sensitivity tables for DCF valuation.

    Table 1: Implied share price across FCF growth × WACC
    Table 2: Terminal value % across terminal growth × WACC
    """

    def build_growth_wacc_table(
        self,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        current_price: float,
        shares_outstanding: float,
        net_debt: float,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
        growth_range: tuple[float, float] = (-0.05, 0.25),
        wacc_range: tuple[float, float] = (0.06, 0.14),
        n_steps: int = 7,
    ) -> SensitivityTable:
        """
        Build implied share price table across growth rate × WACC grid.

        Args:
            fcf_analysis: FCFAnalysis for base FCF.
            wacc_result: WACCResult for base WACC.
            current_price: Current share price (for highlighting).
            shares_outstanding: Diluted shares outstanding.
            net_debt: Total debt minus cash.
            terminal_growth_rate: Terminal growth assumption.
            growth_range: (min, max) FCF growth rates. Default -5% to 25%.
            wacc_range: (min, max) WACC values. Default 6% to 14%.
            n_steps: Number of steps per dimension. Default 7.

        Returns:
            SensitivityTable with implied share prices.
        """
        engine = DCFEngine()

        growth_values = np.linspace(growth_range[0], growth_range[1], n_steps)
        wacc_values = np.linspace(wacc_range[0], wacc_range[1], n_steps)

        # Ensure terminal growth is always < all WACC values. If the requested
        # terminal_growth crowds out the default WACC range, expand the range
        # upward so we still return an n_steps × n_steps table rather than an
        # empty column set (which would break argmin in the caller).
        min_wacc = terminal_growth_rate + 0.01
        if wacc_values.min() <= min_wacc:
            wacc_values = np.linspace(min_wacc, max(wacc_range[1], min_wacc + 0.08), n_steps)

        results = {}
        for g in growth_values:
            row = {}
            for w in wacc_values:
                try:
                    # WACC is passed straight through to _compute_scenario below.
                    scenario = engine._compute_scenario(
                        scenario_name="Sensitivity",
                        growth_rate=float(g),
                        wacc=float(w),
                        fcf_analysis=fcf_analysis,
                        terminal_growth_rate=terminal_growth_rate,
                        horizon=10,
                        current_price=current_price,
                        shares_outstanding=shares_outstanding,
                        net_debt=net_debt,
                        use_ex_sbc=False,
                    )
                    row[round(w, 4)] = round(scenario.intrinsic_value_per_share, 2)
                except (ValueError, ZeroDivisionError):
                    row[round(w, 4)] = float('nan')
            results[round(g, 4)] = row

        table = pd.DataFrame(results).T
        table.index = [f"{g:.1%}" for g in growth_values]
        table.columns = [f"{w:.1%}" for w in wacc_values[:len(table.columns)]]

        return SensitivityTable(
            row_label="FCF Growth Rate",
            col_label="WACC",
            row_values=list(growth_values),
            col_values=list(wacc_values[:len(table.columns)]),
            table=table,
            current_price=current_price,
        )

    def build_terminal_growth_table(
        self,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        current_price: float,
        shares_outstanding: float,
        net_debt: float,
        base_growth_rate: float,
        tg_range: tuple[float, float] = (0.005, 0.030),
        wacc_range: tuple[float, float] = (0.06, 0.14),
        n_steps: int = 6,
    ) -> SensitivityTable:
        """
        Build terminal value sensitivity across terminal growth × WACC.

        Args:
            fcf_analysis: FCFAnalysis.
            wacc_result: WACCResult.
            current_price: Current price.
            shares_outstanding: Shares.
            net_debt: Net debt.
            base_growth_rate: FCF projection growth rate (held constant).
            tg_range: (min, max) terminal growth. Default 0.5% to 3%.
            wacc_range: (min, max) WACC. Default 6% to 14%.
            n_steps: Steps per dimension.

        Returns:
            SensitivityTable with TV% values.
        """
        engine = DCFEngine()

        tg_values = np.linspace(tg_range[0], tg_range[1], n_steps)
        wacc_values = np.linspace(wacc_range[0], wacc_range[1], n_steps)

        results = {}
        for tg in tg_values:
            row = {}
            for w in wacc_values:
                if w <= tg + 0.005:
                    row[round(w, 4)] = float('nan')
                    continue
                try:
                    scenario = engine._compute_scenario(
                        scenario_name="TVSensitivity",
                        growth_rate=float(base_growth_rate),
                        wacc=float(w),
                        fcf_analysis=fcf_analysis,
                        terminal_growth_rate=float(tg),
                        horizon=10,
                        current_price=current_price,
                        shares_outstanding=shares_outstanding,
                        net_debt=net_debt,
                        use_ex_sbc=False,
                    )
                    row[round(w, 4)] = round(scenario.terminal_value_pct * 100, 1)
                except (ValueError, ZeroDivisionError):
                    row[round(w, 4)] = float('nan')
            results[round(tg, 4)] = row

        table = pd.DataFrame(results).T
        table.index = [f"{tg:.1%}" for tg in tg_values]
        table.columns = [f"{w:.1%}" for w in wacc_values[:len(table.columns)]]

        return SensitivityTable(
            row_label="Terminal Growth Rate",
            col_label="WACC",
            row_values=list(tg_values),
            col_values=list(wacc_values[:len(table.columns)]),
            table=table,
            current_price=current_price,
        )

    def generate_plain_language(
        self,
        growth_table: SensitivityTable,
        current_price: float,
        base_growth: float,
        base_wacc: float,
        historical_growth: float,
    ) -> str:
        """
        Generate plain-language interpretation of sensitivity table.

        Tells the user what assumptions justify the current price.
        """
        # Find cells closest to current price
        diff = (growth_table.table - current_price).abs()
        if diff.isna().all().all():
            return "Could not generate sensitivity interpretation."

        min_idx = diff.stack().idxmin()
        closest_growth = min_idx[0]
        closest_wacc = min_idx[1]

        return (
            f"The current price of ${current_price:.0f} is approximately "
            f"justified when FCF grows at {closest_growth} per year "
            f"at a {closest_wacc} discount rate. "
            f"The base case assumes {base_growth:.1%} FCF growth "
            f"at {base_wacc:.1%} WACC. "
            f"Historical median FCF growth has been {historical_growth:.1%}."
        )


