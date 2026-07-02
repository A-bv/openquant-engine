from datetime import datetime
from types import SimpleNamespace

from api.main import _audit_payload, _diagnostic_payload, _red_flags_payload


def _rating(value):
    return SimpleNamespace(value=value)


def test_diagnostic_payload_is_ui_ready():
    diagnostic = SimpleNamespace(
        overall_rating=_rating("amber"),
        total_severity=2,
        summary_text="Two assumptions are flagged.",
        disclaimer="Diagnostic is not a forecast.",
        dimensions=[
            SimpleNamespace(
                name="Beta Reliability",
                rating=_rating("amber"),
                severity=1,
                message="Beta is unstable.",
                detail="Rolling beta moved widely.",
            )
        ],
    )

    payload = _diagnostic_payload(diagnostic)

    assert payload["rating"] == "amber"
    assert payload["total_severity"] == 2
    assert payload["dimensions"][0]["name"] == "Beta Reliability"
    assert payload["dimensions"][0]["rating"] == "amber"


def test_red_flags_payload_is_ui_ready():
    summary = SimpleNamespace(
        flags=["Terminal value is high."],
        has_blocking_issues=False,
        overall_confidence="Moderate",
    )

    payload = _red_flags_payload(summary)

    assert payload == {
        "flags": ["Terminal value is high."],
        "has_blocking_issues": False,
        "overall_confidence": "Moderate",
    }


def test_audit_payload_uses_display_safe_values():
    audit = SimpleNamespace(
        all_warnings=["WACC warning"],
        formula_references=[
            {
                "name": "WACC",
                "formula": "WACC = E/V x rE + D/V x rD x (1-T)",
                "source": "EPFL Formula Sheet",
            }
        ],
        to_display_dict=lambda: {
            "Generated": datetime(2026, 1, 1, 12, 0).strftime("%Y-%m-%d %H:%M UTC"),
            "Company": "Test Co (TEST)",
            "Financial Data": "SEC EDGAR",
            "Price Data": "yfinance",
        },
    )

    payload = _audit_payload(audit)

    assert payload["summary"]["Company"] == "Test Co (TEST)"
    assert payload["formula_references"][0]["name"] == "WACC"
    assert payload["warnings"] == ["WACC warning"]
