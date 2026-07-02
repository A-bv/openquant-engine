"""
OpenQuant — Everyday-money "now vs later" engine tests.

Pinned against the EPFL H1 (PFEM) opening example, the course's own worked
answer for the time value of money — the same role the Sample Exams play for
the other blocks.

PFEM slides 19-20: a $30M lottery paid as 30 x $1M per year starting today,
versus $15M cash today, at an 8% interest rate. The present value of the
payments is $1M + a 29-year annuity = $12.16M, so you take the lump sum.
"""

from __future__ import annotations

import pytest

from openquant.money import compare_now_vs_later


class TestPFEMLottery:
    """The course's worked lottery example is the ground truth."""

    def test_stream_pv_matches_pfem(self):
        r = compare_now_vs_later(
            lump_sum=15_000_000,
            payment=1_000_000,
            n_payments=30,
            rate=0.08,
            first_payment_today=True,
        )
        # PFEM: $1M today + 29-yr annuity at 8% = $12.16M
        assert abs(r.stream_pv - 12_160_000) < 20_000

    def test_verdict_is_take_the_cash(self):
        r = compare_now_vs_later(15_000_000, 1_000_000, 30, 0.08)
        assert r.winner == "now"
        # cash beats the stream by ~$2.84M in today's money
        assert abs(r.advantage - 2_840_000) < 20_000

    def test_nominal_total_is_30m(self):
        r = compare_now_vs_later(15_000_000, 1_000_000, 30, 0.08)
        assert r.nominal_total == 30_000_000

    def test_break_even_rate_exists_and_flips_the_answer(self):
        r = compare_now_vs_later(15_000_000, 1_000_000, 30, 0.08)
        assert r.breakeven_rate is not None
        # below the break-even rate the payments should win
        low = compare_now_vs_later(15_000_000, 1_000_000, 30, r.breakeven_rate - 0.01)
        assert low.winner == "later"


class TestZeroPercentFinancingVsCashDiscount:
    """
    Everyday case: a $20,000 item, "0% over 24 months" ($833.33/mo) versus
    $18,000 cash today. At a 0.5%/month opportunity cost the financed path is
    worth ~$18,800 today, so paying cash is (slightly) better.
    """

    def test_cash_discount_wins_at_positive_rate(self):
        r = compare_now_vs_later(
            lump_sum=18_000,
            payment=20_000 / 24,
            n_payments=24,
            rate=0.005,                 # 0.5% per month
            first_payment_today=False,  # first instalment next month
            kind="pay",                 # this is money you PAY, not receive
        )
        assert r.winner == "now"        # paying $18k cash is cheaper in today's money
        assert 18_500 < r.stream_pv < 19_100


class TestProperties:
    def test_at_zero_rate_stream_pv_equals_nominal(self):
        r = compare_now_vs_later(100, 10, 12, rate=0.0, first_payment_today=False)
        assert abs(r.stream_pv - r.nominal_total) < 1e-6
        assert r.winner == "later"  # 120 nominal > 100 lump

    def test_growing_payments_increase_pv(self):
        flat = compare_now_vs_later(1000, 100, 10, rate=0.05, growth=0.0)
        grow = compare_now_vs_later(1000, 100, 10, rate=0.05, growth=0.03)
        assert grow.stream_pv > flat.stream_pv

    def test_summary_and_detail_render(self):
        r = compare_now_vs_later(15_000_000, 1_000_000, 30, 0.08)
        assert len(r.summary_lines()) == 4
        assert any("PV" in line for line in r.detail_lines())
        assert r.to_dict()["winner"] == "now"

    def test_rejects_bad_inputs(self):
        with pytest.raises(ValueError):
            compare_now_vs_later(100, 10, 0, 0.05)
        with pytest.raises(ValueError):
            compare_now_vs_later(100, 10, 5, -1.5)
