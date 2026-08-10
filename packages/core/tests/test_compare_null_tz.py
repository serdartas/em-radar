from datetime import datetime

from em_radar_core.evaluation.declarative import _compare


def test_between_list_null_returns_false() -> None:
    """Null observed with list date range must return False without raising."""
    assert _compare(None, "between", ["2024-01-01T00:00:00", "2024-06-01T00:00:00"]) is False


def test_between_dict_null_returns_false() -> None:
    """Null observed with dict date range must return False (no phantom finding)."""
    assert (
        _compare(
            None,
            "between",
            {"start": "2024-01-01T00:00:00", "end": "2024-06-01T00:00:00"},
        )
        is False
    )


def test_less_than_null_returns_false() -> None:
    """Null observed must not match less_than any positive number."""
    assert _compare(None, "less_than", 10) is False


def test_before_naive_datetime_returns_true() -> None:
    """Naive observed before tz-aware expected must evaluate without TypeError."""
    assert _compare(datetime(2024, 3, 1), "before", "2024-06-01T00:00:00") is True


def test_after_naive_datetime_returns_false() -> None:
    """Naive observed before tz-aware cutoff must return False for 'after'."""
    assert _compare(datetime(2024, 3, 1), "after", "2024-06-01T00:00:00") is False


def test_between_naive_datetime_within_range_returns_true() -> None:
    """Naive observed within tz-aware date range must evaluate without TypeError."""
    assert (
        _compare(
            datetime(2024, 3, 1),
            "between",
            ["2024-01-01T00:00:00", "2024-06-01T00:00:00"],
        )
        is True
    )


def test_greater_than_null_returns_false() -> None:
    """Null observed must not match greater_than."""
    assert _compare(None, "greater_than", 0) is False


def test_before_null_returns_false() -> None:
    """Null observed must return False for 'before'."""
    assert _compare(None, "before", "2024-06-01T00:00:00") is False


def test_after_null_returns_false() -> None:
    """Null observed must return False for 'after'."""
    assert _compare(None, "after", "2024-01-01T00:00:00") is False


def test_is_before_null_returns_false() -> None:
    """Null observed must return False for 'is_before' (numeric sprint-day style operator)."""
    assert _compare(None, "is_before", 10) is False


def test_is_after_null_returns_false() -> None:
    """Null observed must return False for 'is_after' (numeric sprint-day style operator)."""
    assert _compare(None, "is_after", 0) is False


def test_naive_observed_treated_as_utc_not_reference_tz() -> None:
    """Naive observed (canonical UTC from SQLite round-trip) must be stamped UTC, not reference tz.

    2024-03-01 00:00 UTC is after 2024-03-01T02:00:00+05:00 (≡ 2024-02-29 21:00 UTC).
    If _coerce_tz copied +05:00 instead, observed would become 2024-03-01 00:00+05:00
    (≡ 2024-02-29 19:00 UTC), flipping the comparison result.
    """
    reference_iso = "2024-03-01T02:00:00+05:00"
    observed_naive = datetime(2024, 3, 1, 0, 0, 0)  # stored without tz by SQLite, canonical UTC
    assert _compare(observed_naive, "after", reference_iso) is True
