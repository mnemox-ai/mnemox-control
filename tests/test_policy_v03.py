from decimal import Decimal

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import PolicyBundle, WeeklyWindow
from tests.factories import policy_data


def test_policy_v03_requires_revision_link_shape() -> None:
    policy = PolicyBundle(**policy_data())

    assert policy.version == "0.3"
    assert policy.revision == 1
    assert policy.previous_policy_hash is None


def test_later_revision_requires_previous_hash() -> None:
    data = policy_data()
    data.update(revision=2, previous_policy_hash=None)

    with pytest.raises(ValidationError, match="previous_policy_hash"):
        PolicyBundle(**data)


def test_first_revision_forbids_previous_hash() -> None:
    data = policy_data()
    data["previous_policy_hash"] = "a" * 64

    with pytest.raises(ValidationError, match="previous_policy_hash"):
        PolicyBundle(**data)


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 0), (10, 10), (10080, 10080), (-1, 1), (0, 10081)],
)
def test_weekly_window_requires_non_empty_week_bounds(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        WeeklyWindow(start_minute_utc=start, end_minute_utc=end)


def test_policy_sorts_non_overlapping_windows() -> None:
    data = policy_data()
    data["allowed_weekly_windows"] = (
        {"start_minute_utc": 200, "end_minute_utc": 300},
        {"start_minute_utc": 0, "end_minute_utc": 100},
    )

    policy = PolicyBundle(**data)

    assert tuple(window.start_minute_utc for window in policy.allowed_weekly_windows) == (0, 200)


def test_policy_rejects_overlapping_or_empty_windows() -> None:
    data = policy_data()
    data["allowed_weekly_windows"] = (
        {"start_minute_utc": 0, "end_minute_utc": 100},
        {"start_minute_utc": 99, "end_minute_utc": 200},
    )
    with pytest.raises(ValidationError, match="overlap"):
        PolicyBundle(**data)

    data["allowed_weekly_windows"] = ()
    with pytest.raises(ValidationError):
        PolicyBundle(**data)


def test_full_week_window_is_valid() -> None:
    policy = PolicyBundle(**policy_data())

    assert policy.allowed_weekly_windows == (
        WeeklyWindow(start_minute_utc=0, end_minute_utc=10080),
    )


@pytest.mark.parametrize(
    "field",
    [
        "max_order_notional",
        "max_position_notional",
        "max_daily_loss",
        "max_drawdown",
        "max_state_age_seconds",
        "max_market_age_seconds",
        "max_instrument_age_seconds",
    ],
)
def test_policy_requires_positive_maxima(field: str) -> None:
    data = policy_data()
    data[field] = 0

    with pytest.raises(ValidationError):
        PolicyBundle(**data)


def test_optional_order_quantity_is_positive_when_present() -> None:
    data = policy_data()
    data["max_order_quantity"] = Decimal("0")

    with pytest.raises(ValidationError):
        PolicyBundle(**data)


def test_policy_bounds_non_negative_controls() -> None:
    data = policy_data()
    data["max_price_deviation_bps"] = Decimal("-0.01")
    data["max_open_orders"] = -1

    with pytest.raises(ValidationError):
        PolicyBundle(**data)


def test_policy_hash_is_stable_after_window_normalization() -> None:
    left_data = policy_data()
    left_data["allowed_weekly_windows"] = (
        {"start_minute_utc": 200, "end_minute_utc": 300},
        {"start_minute_utc": 0, "end_minute_utc": 100},
    )
    right_data = policy_data()
    right_data["allowed_weekly_windows"] = (
        {"start_minute_utc": 0, "end_minute_utc": 100},
        {"start_minute_utc": 200, "end_minute_utc": 300},
    )

    left = PolicyBundle(**left_data)
    right = PolicyBundle(**right_data)

    assert content_sha256(left) == content_sha256(right)
