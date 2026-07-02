import json
from pathlib import Path

import pytest

from backtest.analyse import (
    SUMMARY_JSON,
    add_derived,
    calibration_regression,
    headline_numbers,
    load,
    verdict_hit_rate,
)
from api.main import calibration


@pytest.fixture(scope="module")
def backtest_df():
    return add_derived(load())


def test_backtest_fixture_shape(backtest_df):
    assert len(backtest_df) == 50
    assert backtest_df["ticker"].nunique() == 50
    assert backtest_df["iv_base"].notna().sum() == 33


def test_backtest_headline_numbers_are_locked(backtest_df):
    headline = headline_numbers(backtest_df)

    assert headline["data_period"] == "Jan 2014 → Jan 2024"
    assert headline["universe_size"] == 50
    assert headline["successful_runs"] == 33
    assert headline["undervalued"] == {
        "n": 25,
        "mean_realized_annualised_pct": 12.3,
    }
    assert headline["overvalued"] == {
        "n": 6,
        "mean_realized_annualised_pct": 13.6,
    }


def test_backtest_calibration_regression_is_locked(backtest_df):
    reg = calibration_regression(backtest_df)

    assert reg["n"] == 33
    assert reg["slope"] == pytest.approx(0.0023456482)
    assert reg["r_squared"] == pytest.approx(0.0384509938)


def test_backtest_verdict_buckets_are_locked(backtest_df):
    verdicts = verdict_hit_rate(backtest_df)

    assert verdicts["undervalued"]["n"] == 25
    assert verdicts["undervalued"]["hit_rate"] == pytest.approx(0.44)
    assert verdicts["overvalued"]["n"] == 6
    assert verdicts["overvalued"]["hit_rate"] == pytest.approx(2 / 3)
    assert verdicts["model_inapplicable"]["n"] == 9


def test_calibration_summary_json_matches_implemented_metrics(backtest_df):
    saved = json.loads(Path(SUMMARY_JSON).read_text())

    assert saved["headline"] == headline_numbers(backtest_df)
    assert saved["calibration_regression"]["n"] == calibration_regression(backtest_df)["n"]
    assert saved["calibration_regression"]["r_squared"] == pytest.approx(
        calibration_regression(backtest_df)["r_squared"]
    )


def test_calibration_api_payload_exposes_main_product_result():
    payload = calibration()

    assert payload["headline"]["universe_size"] == 50
    assert payload["headline"]["successful_runs"] == 33
    assert payload["calibration_regression"]["r_squared"] == pytest.approx(0.0384509938)
