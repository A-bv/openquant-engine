"""
Calibration analysis — turn the raw backtest CSV into model reliability metrics.

Reads backtest/results/backtest_2014_2024.csv and produces:
  1. Realized return by model value gap bucket
  2. Calibration regression: model value gap % vs realized TSR
  3. Suitability check validity (does AMBER actually correlate with larger errors?)
  4. Sector-level failure-mode analysis
  5. Headline numbers ready to drop into the per-ticker page §9

Output: prints a structured report; also writes JSON summary to
backtest/results/calibration_summary.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RESULTS_CSV = Path(__file__).parent / "results" / "backtest_2014_2024.csv"
SUMMARY_JSON = Path(__file__).parent / "results" / "calibration_summary.json"


def load() -> pd.DataFrame:
    df = pd.read_csv(RESULTS_CSV)
    # numeric coercion
    for c in ["iv_base", "iv_conservative", "iv_optimistic",
              "market_price_as_of", "realized_annualised_return",
              "realized_total_return", "implied_growth",
              "historical_median_growth", "beta", "wacc"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Compute model value gap %, error metrics."""
    df = df.copy()
    df["model_upside_pct"] = (df["iv_base"] / df["market_price_as_of"] - 1.0) * 100
    df["realized_10yr_pct"] = df["realized_annualised_return"] * 100
    return df


def verdict_hit_rate(df: pd.DataFrame) -> dict:
    """
    For each model value gap bucket, report:
      - n (count)
      - mean realized 10yr annualised return
      - vs S&P 500 baseline (~10%/yr 2014-2024)
      - historical reliability check versus the directional model gap
    """
    SP500_TSR = 0.121  # S&P 500 2014-2024 annualised total return, ~12.1%
    results = {}
    for bucket in ["overvalued", "fairly_priced", "undervalued", "model_inapplicable"]:
        sub = df[df["verdict"] == bucket].dropna(subset=["realized_annualised_return"])
        if len(sub) == 0:
            continue
        mean_ret = sub["realized_annualised_return"].mean()
        if bucket == "overvalued":
            hit = (sub["realized_annualised_return"] < SP500_TSR).mean()
            hit_label = f"% underperformed S&P (<{SP500_TSR:.0%})"
        elif bucket == "undervalued":
            hit = (sub["realized_annualised_return"] > SP500_TSR).mean()
            hit_label = f"% outperformed S&P (>{SP500_TSR:.0%})"
        else:
            hit = None
            hit_label = None
        results[bucket] = {
            "n": int(len(sub)),
            "mean_realized_annualised": float(mean_ret),
            "median_realized_annualised": float(sub["realized_annualised_return"].median()),
            "tickers": sub["ticker"].tolist(),
            "hit_rate": float(hit) if hit is not None else None,
            "hit_rate_label": hit_label,
        }
    return results


def calibration_regression(df: pd.DataFrame) -> dict:
    """
    Regress realized 10yr annualised return on model value gap %.
    A well-calibrated model has positive slope and meaningful R².
    """
    sub = df.dropna(subset=["model_upside_pct", "realized_annualised_return"])
    sub = sub[np.isfinite(sub["model_upside_pct"])]
    if len(sub) < 5:
        return {"n": int(len(sub)), "slope": None, "intercept": None, "r_squared": None}
    x = sub["model_upside_pct"].values
    y = sub["realized_annualised_return"].values * 100  # both in pct
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "n": int(len(sub)),
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r2),
        "interpretation": (
            "Slope > 0 means stocks with a higher model value gap later "
            "earned higher returns. R² says how much of the cross-section "
            "the model explains."
        ),
    }


def suitability_validity(df: pd.DataFrame) -> dict:
    """Does AMBER suitability actually correlate with larger model errors?"""
    sub = df.dropna(subset=["iv_base", "market_price_as_of", "realized_annualised_return"])
    sub = sub.copy()
    sub["abs_error_pct"] = (sub["iv_base"] / sub["market_price_as_of"] - 1.0).abs() * 100
    out = {}
    for rating in ["green", "amber", "red", "error"]:
        sub_r = sub[sub["suitability_rating"] == rating]
        if len(sub_r) == 0:
            continue
        out[rating] = {
            "n": int(len(sub_r)),
            "mean_abs_error_pct": float(sub_r["abs_error_pct"].mean()),
            "median_abs_error_pct": float(sub_r["abs_error_pct"].median()),
        }
    return out


def sector_breakdown(df: pd.DataFrame) -> dict:
    """For each sector, mean absolute error in model gap vs realized return."""
    sub = df.dropna(subset=["model_upside_pct", "realized_annualised_return"])
    sub = sub.copy()
    sub["pred_return_pct"] = sub["model_upside_pct"]  # 10-yr model value gap
    sub["realized_pct"] = sub["realized_annualised_return"] * 100 * 10  # 10yr realized total
    sub["error_pp"] = sub["realized_pct"] - sub["pred_return_pct"]
    out = {}
    for sector, sub_s in sub.groupby("sector"):
        out[sector] = {
            "n": int(len(sub_s)),
            "mean_predicted_upside_pct": float(sub_s["pred_return_pct"].mean()),
            "mean_realized_10yr_pct": float(sub_s["realized_pct"].mean()),
            "mean_error_pp": float(sub_s["error_pp"].mean()),
        }
    return out


def headline_numbers(df: pd.DataFrame) -> dict:
    """
    The 3 numbers we put in §9 of the per-ticker page.
    """
    verdicts = verdict_hit_rate(df)
    out = {
        "data_period": "Jan 2014 → Jan 2024",
        "universe_size": int(len(df)),
        "successful_runs": int(len(df.dropna(subset=["iv_base"]))),
    }
    if "undervalued" in verdicts:
        out["undervalued"] = {
            "n": verdicts["undervalued"]["n"],
            "mean_realized_annualised_pct": round(verdicts["undervalued"]["mean_realized_annualised"] * 100, 1),
        }
    if "overvalued" in verdicts:
        out["overvalued"] = {
            "n": verdicts["overvalued"]["n"],
            "mean_realized_annualised_pct": round(verdicts["overvalued"]["mean_realized_annualised"] * 100, 1),
        }
    if "fairly_priced" in verdicts:
        out["fairly_priced"] = {
            "n": verdicts["fairly_priced"]["n"],
            "mean_realized_annualised_pct": round(verdicts["fairly_priced"]["mean_realized_annualised"] * 100, 1),
        }
    return out


def main() -> None:
    df = load()
    df = add_derived(df)

    summary = {
        "headline": headline_numbers(df),
        "verdict_hit_rate": verdict_hit_rate(df),
        "calibration_regression": calibration_regression(df),
        "suitability_validity": suitability_validity(df),
        "sector_breakdown": sector_breakdown(df),
        "failure_log": df[df["error"].notna()][["ticker", "sector", "error"]].to_dict("records"),
    }

    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Saved summary → {SUMMARY_JSON}\n")

    # Human-readable digest
    h = summary["headline"]
    print(f"Backtest: {h['data_period']}")
    print(f"Universe: {h['universe_size']} stocks, {h['successful_runs']} ran cleanly")
    print()
    print("Model value gap outcomes:")
    for k in ["overvalued", "fairly_priced", "undervalued"]:
        v = summary["verdict_hit_rate"].get(k)
        if not v:
            continue
        print(f"  {k:18s} n={v['n']:2d}  mean realized = {v['mean_realized_annualised']*100:+5.1f}%/yr"
              f"  {v.get('hit_rate_label') or ''}: "
              f"{v['hit_rate']*100:.0f}%" if v.get('hit_rate') is not None else "")
    print()
    reg = summary["calibration_regression"]
    if reg.get("slope") is not None:
        print(f"Calibration regression (n={reg['n']}):")
        print(f"  slope     = {reg['slope']:+.4f}  (1pp more upside → {reg['slope']:+.3f}pp more realized return)")
        print(f"  intercept = {reg['intercept']:+.2f}")
        print(f"  R²        = {reg['r_squared']:.3f}")
    print()
    print("Suitability-error correlation:")
    for rating, stats in summary["suitability_validity"].items():
        print(f"  {rating:8s} n={stats['n']:2d}  median |error| = {stats['median_abs_error_pct']:>6.1f}%")
    print()
    print("Sector breakdown (model value gap vs realized 10yr total):")
    for sector, stats in summary["sector_breakdown"].items():
        print(f"  {sector:12s} n={stats['n']:2d}  pred={stats['mean_predicted_upside_pct']:>+7.0f}%  realized={stats['mean_realized_10yr_pct']:>+7.0f}%  error={stats['mean_error_pp']:>+7.0f}pp")
    print()
    if summary["failure_log"]:
        print(f"Failures: {len(summary['failure_log'])}")
        for f in summary["failure_log"]:
            print(f"  {f['ticker']} ({f['sector']}): {f['error']}")


if __name__ == "__main__":
    main()
