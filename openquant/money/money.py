"""
OpenQuant — Everyday-money decision engine (H1 / time value of money).

Pure Python. No network, no Streamlit. Reuses the exam-pinned DCFEngine.npv.

Turns the EPFL H1 (PFEM) "time value of money" block into one concrete,
universal deliverable that needs no market data and cannot fail on a ticker:

    "Take the money now, or the bigger amount spread over time?"

This is the course's own opening example (PFEM slides 19-20): a $30M lottery
paid as 30 x $1M/yr is worth only $12.16M today at 8% — less than $15M cash.

Two-layer design:
  Layer 1 — NowVsLaterResult.summary_lines(): the verdict + the one assumption.
  Layer 2 — .detail_lines(): the PV of each payment, the break-even rate, the
            formula and the EPFL source.

Validated against the PFEM lottery in tests/test_money.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from scipy.optimize import brentq

from openquant.common import format_currency, format_percent
from openquant.valuation.dcf import DCFEngine

_ENGINE = DCFEngine()


# ── Cash-flow construction ────────────────────────────────────────────────────

def _stream_flows(
    payment: float,
    n_payments: int,
    growth: float,
    first_payment_today: bool,
) -> tuple[list[float], list[tuple[int, float]]]:
    """
    Build the payment stream as an npv()-ready list (index = period t) and a
    parallel (t, amount) table for Layer-2 rendering.

    Payments grow at `growth` per period. First payment lands at t=0 if
    first_payment_today else t=1.
    """
    flows: dict[int, float] = {}
    for k in range(n_payments):
        t = k if first_payment_today else k + 1
        flows[t] = payment * (1 + growth) ** k
    max_t = max(flows)
    cashflows = [flows.get(t, 0.0) for t in range(max_t + 1)]
    return cashflows, sorted(flows.items())


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class NowVsLaterResult:
    """The "now vs later" deliverable, structured for two-layer rendering."""
    lump_sum: float
    payment: float
    n_payments: int
    rate: float
    growth: float
    first_payment_today: bool
    kind: str                 # "receive" (take the bigger) or "pay" (take the cheaper)
    currency: str

    stream_pv: float          # present value of the payment stream
    nominal_total: float      # undiscounted sum of the payments
    winner: str               # "now" (lump) or "later" (stream)
    advantage: float          # |lump - stream_pv|, in today's money
    breakeven_rate: Optional[float]   # rate where the two are equal
    _flow_table: list[tuple[int, float]]

    def summary_lines(self) -> list[str]:
        """Layer 1 — the plain verdict for the general public."""
        now = format_currency(self.lump_sum, self.currency)
        later_pv = format_currency(self.stream_pv, self.currency)
        nominal = format_currency(self.nominal_total, self.currency)
        adv = format_currency(self.advantage, self.currency)

        if self.kind == "pay":
            verdict = (
                f"Pay the {now} cash now." if self.winner == "now"
                else "Take the financing, spread it out."
            )
            middle = (
                f"Paying over time totals {nominal} on paper, but in today's "
                f"money it costs {later_pv}."
            )
            who = "Paying cash" if self.winner == "now" else "Financing"
            lines = [verdict, middle, f"{who} saves {adv} in today's money."]
        else:
            verdict = f"Take the {now} now." if self.winner == "now" else "Take the payments."
            middle = (
                f"The payments add up to {nominal} on paper, but in today's "
                f"money they're worth {later_pv}."
            )
            who = "The cash" if self.winner == "now" else "The payments"
            lines = [verdict, middle, f"{who} wins by {adv} in today's money."]
        assumption = (
            f"This assumes your own money is worth {format_percent(self.rate)}/yr to you"
        )
        if self.breakeven_rate is not None:
            flips = "below" if self.winner == "now" else "above"
            assumption += (
                f". {flips.capitalize()} {format_percent(self.breakeven_rate)}/yr the answer flips."
            )
        else:
            assumption += "."
        lines.append(assumption)
        return lines

    def detail_lines(self) -> list[str]:
        """Layer 2 — the present-value work, break-even, formula, source."""
        rows = []
        shown = self._flow_table if len(self._flow_table) <= 8 else (
            self._flow_table[:4] + [(-1, None)] + self._flow_table[-2:]
        )
        for t, amt in shown:
            if amt is None:
                rows.append("    ...")
                continue
            df = 1.0 / (1 + self.rate) ** t
            pv = amt * df
            rows.append(
                f"    t={t:<3} {format_currency(amt, self.currency):>12}"
                f"  x {df:6.4f}  = {format_currency(pv, self.currency):>12}"
            )
        out = [
            "Present value of each payment (PV = CF / (1+r)^t):",
            *rows,
            f"    {'Total (PV of stream)':<20} = "
            f"{format_currency(self.stream_pv, self.currency)}",
            "",
            f"Versus taking {format_currency(self.lump_sum, self.currency)} today.",
        ]
        if self.breakeven_rate is not None:
            out.append(
                f"Break-even rate: {format_percent(self.breakeven_rate)}. The two "
                f"options are worth exactly the same at this discount rate."
            )
        out += [
            "",
            "Source: Berk-DeMarzo Ch. 4 · formula sheet p.1 · PFEM slides 17-20",
            "  PV(stream) = Σ CFt / (1+r)^t   (value additivity / DCF)",
            "Pinned against the PFEM lottery ($30M as 30x$1M ≈ $12.16M at 8%) "
            "in tests/test_money.py.",
        ]
        return out

    def to_dict(self) -> dict:
        return {
            "lump_sum": float(self.lump_sum),
            "payment": float(self.payment),
            "n_payments": int(self.n_payments),
            "rate": float(self.rate),
            "growth": float(self.growth),
            "first_payment_today": bool(self.first_payment_today),
            "kind": self.kind,
            "currency": self.currency,
            "stream_pv": float(self.stream_pv),
            "nominal_total": float(self.nominal_total),
            "winner": self.winner,
            "advantage": float(self.advantage),
            "breakeven_rate": (
                None if self.breakeven_rate is None else float(self.breakeven_rate)
            ),
            "flow_table": [
                {"t": int(t), "amount": float(a)} for t, a in self._flow_table
            ],
        }


# ── Engine ────────────────────────────────────────────────────────────────────

def compare_now_vs_later(
    lump_sum: float,
    payment: float,
    n_payments: int,
    rate: float,
    growth: float = 0.0,
    first_payment_today: bool = True,
    kind: str = "receive",
    currency: str = "$",
) -> NowVsLaterResult:
    """
    Decide between a lump sum today and a stream of `n_payments` payments.

    Args:
        lump_sum: amount offered today.
        payment: the first periodic payment (grows by `growth` thereafter).
        n_payments: number of payments.
        rate: the discount rate = how much money-now is worth to you (per period).
        growth: per-period growth of the payments (0 for level payments).
        first_payment_today: True if the first payment lands now (t=0).
        currency: symbol for display.

    Returns:
        NowVsLaterResult (Layer 1 + Layer 2).
    """
    if n_payments < 1:
        raise ValueError("n_payments must be at least 1")
    if rate <= -1:
        raise ValueError("rate must be greater than -100%")
    if lump_sum < 0 or payment < 0:
        raise ValueError("amounts must be non-negative")
    if kind not in ("receive", "pay"):
        raise ValueError("kind must be 'receive' or 'pay'")

    cashflows, flow_table = _stream_flows(payment, n_payments, growth, first_payment_today)
    stream_pv = _ENGINE.npv(cashflows, rate)
    nominal_total = sum(amt for _, amt in flow_table)

    # When you RECEIVE money, the bigger present value wins. When you PAY,
    # the smaller present value (cheaper in today's money) wins.
    if kind == "pay":
        winner = "now" if lump_sum <= stream_pv else "later"
    else:
        winner = "now" if lump_sum >= stream_pv else "later"
    advantage = abs(lump_sum - stream_pv)

    # Break-even rate: the r where PV(stream, r) == lump_sum.
    breakeven_rate: Optional[float] = None
    try:
        def f(r):
            return _ENGINE.npv(cashflows, r) - lump_sum
        lo, hi = -0.99, 5.0
        if f(lo) * f(hi) < 0:
            breakeven_rate = float(brentq(f, lo, hi, xtol=1e-8))
    except Exception:
        breakeven_rate = None

    return NowVsLaterResult(
        lump_sum=lump_sum,
        payment=payment,
        n_payments=n_payments,
        rate=rate,
        growth=growth,
        first_payment_today=first_payment_today,
        kind=kind,
        currency=currency,
        stream_pv=stream_pv,
        nominal_total=nominal_total,
        winner=winner,
        advantage=advantage,
        breakeven_rate=breakeven_rate,
        _flow_table=flow_table,
    )
