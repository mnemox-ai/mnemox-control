from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from mnemox_control.calculations import (
    CalculationCoverageError,
    build_exposure_metrics,
    classify_position_effect,
    is_step_aligned,
    reference_price,
    signed_order_quantity,
)
from mnemox_control.contracts import OrderIntent
from mnemox_control.evaluation import PositionEffect
from mnemox_control.state import (
    InstrumentCatalog,
    InstrumentSpec,
    MarketQuote,
    MarketSnapshot,
    OpenOrderStatus,
)
from tests.factories import buy, buy_intent, catalog_btc, market_btc, sell


@pytest.mark.parametrize(
    ("current", "delta", "expected"),
    [
        ("0", "1", "OPEN"),
        ("1", "1", "INCREASE"),
        ("2", "-1", "REDUCE"),
        ("1", "-1", "CLOSE"),
        ("1", "-2", "REVERSE"),
        ("-1", "-1", "INCREASE"),
        ("-2", "1", "REDUCE"),
        ("-1", "2", "REVERSE"),
    ],
)
def test_classifies_position_effect(current: str, delta: str, expected: str) -> None:
    proposed = Decimal(current) + Decimal(delta)

    assert classify_position_effect(Decimal(current), proposed).value == expected


def test_unchanged_position_has_no_effect_class() -> None:
    with pytest.raises(ValueError, match="unchanged"):
        classify_position_effect(Decimal("1"), Decimal("1"))


def test_signed_order_quantity_uses_side() -> None:
    buy_order = buy_intent("BTCUSDT", "2")
    sell_order = buy_order.model_copy(update={"side": "SELL"})

    assert signed_order_quantity(buy_order) == Decimal("2")
    assert signed_order_quantity(sell_order) == Decimal("-2")


@pytest.mark.parametrize(
    ("side", "expected"),
    [("BUY", Decimal("101")), ("SELL", Decimal("99"))],
)
def test_market_reference_price_uses_adverse_book_side(side: str, expected: Decimal) -> None:
    intent = buy_intent("BTCUSDT", "1").model_copy(update={"side": side})
    quote = MarketQuote(symbol="BTCUSDT", bid="99", ask="101", mark="100")

    assert reference_price(intent, quote) == expected


@pytest.mark.parametrize(
    ("order_type", "price_field", "expected"),
    [("LIMIT", "limit_price", "102.5"), ("STOP", "stop_price", "97.5")],
)
def test_declared_order_price_is_reference(
    order_type: str, price_field: str, expected: str
) -> None:
    data = buy_intent("BTCUSDT", "1").model_dump()
    data.update(order_type=order_type, **{price_field: expected})
    intent = OrderIntent(**data)

    assert reference_price(
        intent,
        MarketQuote(symbol="BTCUSDT", bid="99", ask="101", mark="100"),
    ) == Decimal(expected)


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [("1.200", "0.001", True), ("1.2001", "0.001", False), ("0", "0.1", True)],
)
def test_step_alignment_uses_exact_decimal_modulo(
    value: str, step: str, expected: bool
) -> None:
    assert is_step_aligned(Decimal(value), Decimal(step)) is expected


def test_step_alignment_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="positive"):
        is_step_aligned(Decimal("1"), Decimal("0"))


def test_opposite_pending_orders_use_larger_absolute_envelope() -> None:
    metrics = build_exposure_metrics(
        current={"BTCUSDT": Decimal("1")},
        pending=(buy("BTCUSDT", "2"), sell("BTCUSDT", "4")),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog_btc(multiplier="1"),
        market=market_btc(mark="100"),
        equity=Decimal("1000"),
    )

    assert metrics.worst_case_position_quantities["BTCUSDT"] == Decimal("4")
    assert metrics.projected_gross_exposure == Decimal("404")
    assert metrics.projected_leverage == Decimal("0.404")


def test_reduce_only_orders_do_not_reduce_capacity_envelope() -> None:
    existing_reducer = sell("BTCUSDT", "1").model_copy(update={"reduce_only": True})
    proposed_reducer = buy_intent("BTCUSDT", "1").model_copy(
        update={"side": "SELL", "reduce_only": True}
    )

    metrics = build_exposure_metrics(
        current={"BTCUSDT": Decimal("2")},
        pending=(existing_reducer,),
        proposed=proposed_reducer,
        catalog=catalog_btc(),
        market=market_btc(),
        equity=Decimal("1000"),
    )

    assert metrics.proposed_fill_position_quantity == Decimal("1")
    assert metrics.position_effect is PositionEffect.REDUCE
    assert metrics.worst_case_position_quantities["BTCUSDT"] == Decimal("2")
    assert metrics.projected_gross_exposure == Decimal("200")


def test_pending_reference_price_conservatively_values_exposure() -> None:
    expensive_pending = buy("BTCUSDT", "1").model_copy(update={"reference_price": Decimal("120")})

    metrics = build_exposure_metrics(
        current={},
        pending=(expensive_pending,),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog_btc(multiplier="2"),
        market=market_btc(mark="100"),
        equity=Decimal("1000"),
    )

    assert metrics.worst_case_position_quantities["BTCUSDT"] == Decimal("2")
    assert metrics.worst_case_position_notional == Decimal("480")


def test_all_symbols_contribute_to_gross_exposure() -> None:
    btc = catalog_btc().instruments[0]
    eth = InstrumentSpec(
        **{
            **btc.model_dump(),
            "instrument_id": "binance:ETHUSDT",
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
        }
    )
    catalog = InstrumentCatalog(
        catalog_id=UUID("66666666-6666-6666-6666-666666666666"),
        version="2026-08-30",
        broker="binance-demo",
        instruments=(btc, eth),
        observed_at=datetime(2026, 8, 30, 11, 59, 45, tzinfo=UTC),
    )
    market = MarketSnapshot(
        snapshot_id=UUID("77777777-7777-7777-7777-777777777777"),
        source="test-market",
        quotes=(
            MarketQuote(symbol="BTCUSDT", bid="99", ask="101", mark="100"),
            MarketQuote(symbol="ETHUSDT", bid="49", ask="51", mark="50"),
        ),
        observed_at=datetime(2026, 8, 30, 11, 59, 50, tzinfo=UTC),
    )

    metrics = build_exposure_metrics(
        current={"BTCUSDT": Decimal("1"), "ETHUSDT": Decimal("2")},
        pending=(),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog,
        market=market,
        equity=Decimal("1000"),
    )

    assert metrics.projected_gross_exposure == Decimal("302")


def test_missing_coverage_lists_all_unvalued_symbols() -> None:
    with pytest.raises(CalculationCoverageError) as error:
        build_exposure_metrics(
            current={"BTCUSDT": Decimal("1"), "ETHUSDT": Decimal("2")},
            pending=(buy("SOLUSDT", "3"),),
            proposed=buy_intent("BTCUSDT", "1"),
            catalog=catalog_btc(),
            market=market_btc(),
            equity=Decimal("1000"),
        )

    assert error.value.missing_instruments == ("ETHUSDT", "SOLUSDT")
    assert error.value.missing_quotes == ("ETHUSDT", "SOLUSDT")


def test_non_positive_equity_leaves_only_leverage_undefined() -> None:
    metrics = build_exposure_metrics(
        current={},
        pending=(),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog_btc(),
        market=market_btc(),
        equity=Decimal("0"),
    )

    assert metrics.projected_gross_exposure == Decimal("101")
    assert metrics.projected_leverage is None
    assert all(not isinstance(value, float) for value in metrics.__dict__.values())


@pytest.mark.parametrize("status", list(OpenOrderStatus))
def test_every_non_terminal_order_status_counts_in_full(status: OpenOrderStatus) -> None:
    pending = buy("BTCUSDT", "1").model_copy(update={"status": status})

    metrics = build_exposure_metrics(
        current={},
        pending=(pending,),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog_btc(),
        market=market_btc(),
        equity=Decimal("1000"),
    )

    assert metrics.worst_case_position_quantities["BTCUSDT"] == Decimal("2")
    assert metrics.projected_gross_exposure == Decimal("202")
