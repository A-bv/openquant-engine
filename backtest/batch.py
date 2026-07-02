"""
Run the full 50-stock backtest in one shot.

Walks the universe sequentially (parallel would be nice but SEC rate-limits
to 10 req/s and each ticker fans out to ~5 EDGAR calls), runs the model
"as of" the configured date, computes realised return through the horizon,
and writes results to CSV.

Usage:
    python -m backtest.batch                    # full 50-ticker backtest
    python -m backtest.batch --limit 5          # smoke test on first 5
    python -m backtest.batch --tickers AAPL,MSFT  # specific tickers
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from backtest.run import BacktestRow, analyse_as_of, compute_realized
from backtest.universe import TICKERS, BACKTEST_UNIVERSE

AS_OF = date(2014, 1, 31)
HORIZON = date(2024, 1, 31)
RESULTS_DIR = Path(__file__).parent / "results"


def run_one(ticker: str) -> BacktestRow:
    t0 = time.monotonic()
    row = analyse_as_of(ticker, AS_OF)
    row = compute_realized(row, HORIZON)
    dt = time.monotonic() - t0
    if row.error:
        status = f"❌ {row.error}"
    else:
        iv_base = f"${row.iv_base:.2f}" if row.iv_base else "n/a"
        price = f"${row.market_price_as_of:.2f}"
        rtsr = (
            f"{row.realized_annualised_return * 100:+.1f}%/yr"
            if row.realized_annualised_return is not None
            else "n/a"
        )
        status = f"price {price} · IV base {iv_base} · verdict {row.verdict} · realized {rtsr}"
    print(f"  [{dt:5.1f}s] {ticker:6s} {status}", flush=True)
    return row


def save_csv(rows: list[BacktestRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    field_names = [f.name for f in fields(BacktestRow)]
    # Add sector column from universe for downstream analysis
    field_names_out = ["sector", *field_names]
    sector_lookup = {t: s for t, s, _ in BACKTEST_UNIVERSE}
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names_out)
        writer.writeheader()
        for r in rows:
            d = asdict(r)
            d["sector"] = sector_lookup.get(r.ticker, "")
            writer.writerow(d)
    print(f"\nSaved {len(rows)} rows → {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run first N tickers (for smoke testing)")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated tickers (override universe)")
    ap.add_argument("--output", type=str, default=str(RESULTS_DIR / "backtest_2014_2024.csv"))
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        tickers = TICKERS
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"Running backtest: as_of={AS_OF}, horizon={HORIZON}, n_tickers={len(tickers)}")
    print("=" * 80)
    rows = []
    overall = time.monotonic()
    for i, t in enumerate(tickers, 1):
        print(f"[{i:2d}/{len(tickers)}]", end=" ")
        rows.append(run_one(t))
    elapsed = time.monotonic() - overall
    print("=" * 80)
    print(f"Done in {elapsed/60:.1f} minutes ({elapsed/len(tickers):.1f}s/ticker)")

    save_csv(rows, Path(args.output))

    # Quick summary
    successes = [r for r in rows if not r.error]
    errors = [r for r in rows if r.error]
    print(f"\nSuccess: {len(successes)}/{len(rows)} ({len(successes)/len(rows)*100:.0f}%)")
    if errors:
        print(f"Failures: {len(errors)}")
        for r in errors:
            print(f"  {r.ticker}: {r.error}")

    if successes:
        from collections import Counter
        verdicts = Counter(r.verdict for r in successes)
        print(f"\nVerdict distribution:")
        for v, c in verdicts.most_common():
            print(f"  {v or '(none)':20s} {c:3d}")


if __name__ == "__main__":
    main()
