from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import PolicyBundle


def valid_policy_data() -> dict[str, object]:
    return {
        "policy_id": UUID("11111111-1111-1111-1111-111111111111"),
        "version": "0.3",
        "revision": 1,
        "previous_policy_hash": None,
        "owner_id": "owner-1",
        "account_id": "account-1",
        "broker": "binance-demo",
        "allowed_symbols": ("BTCUSDT", "ETHUSDT"),
        "max_order_notional": Decimal("1000"),
        "max_position_notional": Decimal("5000"),
        "max_leverage": Decimal("3"),
        "max_daily_loss": Decimal("100"),
        "max_drawdown": Decimal("500"),
        "approval_notional": Decimal("750"),
        "max_state_age_seconds": 60,
        "max_market_age_seconds": 30,
        "max_instrument_age_seconds": 86400,
        "max_price_deviation_bps": Decimal("100"),
        "max_open_orders": 10,
        "max_order_quantity": None,
        "require_protective_stop": False,
        "allow_position_reversal": False,
        "risk_day_start_hour_utc": 0,
        "allowed_weekly_windows": ({"start_minute_utc": 0, "end_minute_utc": 10080},),
        "created_at": datetime(2026, 8, 30, 7, tzinfo=UTC),
        "valid_from": datetime(2026, 8, 30, 16, tzinfo=timezone(timedelta(hours=8))),
        "expires_at": datetime(2026, 9, 30, 8, tzinfo=UTC),
    }


def test_policy_normalizes_symbols_timestamps_and_hashes_without_mutation() -> None:
    data = valid_policy_data()
    data["allowed_symbols"] = (" btcusdt ", "ETHUSDT", "BTCUSDT")
    policy = PolicyBundle(**data)

    hashed = policy.with_content_hash()

    assert policy.allowed_symbols == ("BTCUSDT", "ETHUSDT")
    assert policy.valid_from == datetime(2026, 8, 30, 8, tzinfo=UTC)
    assert policy.content_hash is None
    assert hashed.content_hash == content_sha256(policy, exclude={"content_hash"})


def test_policy_rejects_approval_above_order_limit() -> None:
    data = valid_policy_data()
    data["approval_notional"] = Decimal("1001")

    with pytest.raises(ValidationError, match="approval_notional"):
        PolicyBundle(**data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_order_notional", Decimal("-1")),
        ("max_position_notional", Decimal("-1")),
        ("max_leverage", Decimal("0.99")),
        ("max_daily_loss", Decimal("-1")),
        ("max_drawdown", Decimal("-1")),
    ],
)
def test_policy_rejects_invalid_limits(field: str, value: Decimal) -> None:
    data = valid_policy_data()
    data[field] = value

    with pytest.raises(ValidationError):
        PolicyBundle(**data)


def test_policy_rejects_invalid_time_window() -> None:
    data = valid_policy_data()
    data["expires_at"] = data["valid_from"]

    with pytest.raises(ValidationError, match="expires_at"):
        PolicyBundle(**data)


def test_policy_rejects_blank_identity_unknown_fields_and_mutation() -> None:
    data = valid_policy_data()
    data["owner_id"] = "  "
    data["surprise"] = True

    with pytest.raises(ValidationError):
        PolicyBundle(**data)

    policy = PolicyBundle(**valid_policy_data())
    with pytest.raises(ValidationError):
        policy.owner_id = "changed"  # type: ignore[misc]
