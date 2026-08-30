from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import OrderIntent


def valid_intent_data() -> dict[str, object]:
    return {
        "intent_id": UUID("22222222-2222-2222-2222-222222222222"),
        "agent_id": "agent-1",
        "account_id": "account-1",
        "broker": "binance-demo",
        "symbol": " btcusdt ",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": Decimal("0.01"),
        "limit_price": None,
        "stop_price": None,
        "reduce_only": False,
        "strategy_id": "strategy-1",
        "reason": "Trend and risk gates passed",
        "market_data_as_of": datetime(2026, 8, 30, 8, tzinfo=timezone.utc),
        "created_at": datetime(2026, 8, 30, 8, 0, 1, tzinfo=timezone.utc),
    }


def test_market_order_normalizes_symbol_and_hashes_stably() -> None:
    left = OrderIntent(**valid_intent_data())
    right = OrderIntent(**dict(reversed(list(valid_intent_data().items()))))

    assert left.symbol == "BTCUSDT"
    assert content_sha256(left) == content_sha256(right)


@pytest.mark.parametrize(
    ("order_type", "limit_price", "stop_price", "message"),
    [
        ("LIMIT", None, None, "limit_price"),
        ("STOP", None, None, "stop_price"),
        ("MARKET", Decimal("100"), None, "MARKET"),
        ("MARKET", None, Decimal("100"), "MARKET"),
        ("LIMIT", Decimal("100"), Decimal("99"), "LIMIT"),
        ("STOP", Decimal("100"), Decimal("99"), "STOP"),
    ],
)
def test_order_type_enforces_exact_price_shape(
    order_type: str,
    limit_price: Decimal | None,
    stop_price: Decimal | None,
    message: str,
) -> None:
    data = valid_intent_data()
    data.update(order_type=order_type, limit_price=limit_price, stop_price=stop_price)

    with pytest.raises(ValidationError, match=message):
        OrderIntent(**data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Decimal("0")),
        ("quantity", Decimal("-1")),
        ("agent_id", " "),
        ("strategy_id", ""),
        ("reason", " "),
    ],
)
def test_order_intent_rejects_invalid_values(field: str, value: object) -> None:
    data = valid_intent_data()
    data[field] = value

    with pytest.raises(ValidationError):
        OrderIntent(**data)


def test_limit_and_stop_orders_accept_their_required_price() -> None:
    limit_data = valid_intent_data()
    limit_data.update(order_type="LIMIT", limit_price=Decimal("100"))
    stop_data = valid_intent_data()
    stop_data.update(order_type="STOP", stop_price=Decimal("99"))

    assert OrderIntent(**limit_data).limit_price == Decimal("100")
    assert OrderIntent(**stop_data).stop_price == Decimal("99")


def test_order_intent_rejects_unknown_fields_and_mutation() -> None:
    data = valid_intent_data()
    data["surprise"] = True
    with pytest.raises(ValidationError):
        OrderIntent(**data)

    intent = OrderIntent(**valid_intent_data())
    with pytest.raises(ValidationError):
        intent.symbol = "ETHUSDT"  # type: ignore[misc]
