from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.state import (
    HaltState,
    InstrumentCatalog,
    InstrumentSpec,
    InstrumentType,
    MarketQuote,
    MarketSnapshot,
    OpenOrderExposure,
    OpenOrderStatus,
    Position,
    PositionMode,
    TrustedAccountSnapshot,
)


@pytest.fixture
def valid_instrument_data() -> dict[str, object]:
    return {
        "instrument_id": "binance:BTCUSDT",
        "version": "2026-08-30",
        "broker": "binance-demo",
        "symbol": "BTCUSDT",
        "instrument_type": "LINEAR_PERPETUAL",
        "position_mode": "ONE_WAY",
        "allows_short": True,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "contract_multiplier": Decimal("1"),
        "quantity_step": Decimal("0.001"),
        "price_tick": Decimal("0.1"),
        "min_quantity": Decimal("0.001"),
        "min_notional": Decimal("5"),
    }


@pytest.fixture
def valid_instrument(valid_instrument_data: dict[str, object]) -> InstrumentSpec:
    return InstrumentSpec(**valid_instrument_data)


@pytest.fixture
def valid_catalog(valid_instrument: InstrumentSpec) -> InstrumentCatalog:
    return InstrumentCatalog(
        catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
        version="2026-08-30",
        broker="binance-demo",
        instruments=(valid_instrument,),
        observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
    )


@pytest.fixture
def valid_quote() -> MarketQuote:
    return MarketQuote(symbol="BTCUSDT", bid="99", ask="101", mark="100")


def market_data(*, quotes: tuple[MarketQuote, ...]) -> dict[str, object]:
    return {
        "snapshot_id": UUID("018f84d7-46a7-7e8d-97de-4a3f13635d41"),
        "source": "binance-market-data",
        "quotes": quotes,
        "observed_at": datetime(
            2026,
            8,
            30,
            16,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    }


@pytest.fixture
def valid_account_data() -> dict[str, object]:
    return {
        "snapshot_id": UUID("018f84d7-46a7-7e8d-97de-4a3f13635d42"),
        "state_version": 7,
        "source": "binance-user-stream",
        "account_id": "paper-1",
        "broker": "binance-demo",
        "equity": Decimal("10000"),
        "cash_balance": Decimal("10000"),
        "realized_pnl_today": Decimal("0"),
        "realized_pnl_period_start": datetime(2026, 8, 30, tzinfo=UTC),
        "realized_pnl_period_end": datetime(2026, 8, 31, tzinfo=UTC),
        "drawdown_from_peak": Decimal("0"),
        "positions": (),
        "open_orders": (),
        "halt_state": "NORMAL",
        "observed_at": datetime(2026, 8, 30, 8, tzinfo=UTC),
    }


def test_instrument_normalizes_wire_identifiers(
    valid_instrument_data: dict[str, object],
) -> None:
    valid_instrument_data.update(symbol=" btcusdt ", base_asset=" btc ", quote_asset=" usdt ")

    instrument = InstrumentSpec(**valid_instrument_data)

    assert instrument.symbol == "BTCUSDT"
    assert instrument.base_asset == "BTC"
    assert instrument.quote_asset == "USDT"
    assert instrument.instrument_type is InstrumentType.LINEAR_PERPETUAL
    assert instrument.position_mode is PositionMode.ONE_WAY


@pytest.mark.parametrize(
    "field",
    ["contract_multiplier", "quantity_step", "price_tick", "min_quantity", "min_notional"],
)
def test_instrument_requires_positive_numeric_constraints(
    valid_instrument_data: dict[str, object], field: str
) -> None:
    valid_instrument_data[field] = Decimal("0")

    with pytest.raises(ValidationError):
        InstrumentSpec(**valid_instrument_data)


def test_catalog_rejects_duplicate_symbols(valid_instrument: InstrumentSpec) -> None:
    duplicate = valid_instrument.model_copy(update={"instrument_id": "binance:BTCUSDT:second"})

    with pytest.raises(ValidationError, match="unique"):
        InstrumentCatalog(
            catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
            version="2026-08-30",
            broker="binance-demo",
            instruments=(valid_instrument, duplicate),
            observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
        )


def test_catalog_rejects_duplicate_instrument_ids(valid_instrument: InstrumentSpec) -> None:
    duplicate = valid_instrument.model_copy(update={"symbol": "ETHUSDT"})

    with pytest.raises(ValidationError, match="unique"):
        InstrumentCatalog(
            catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
            version="2026-08-30",
            broker="binance-demo",
            instruments=(valid_instrument, duplicate),
            observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
        )


def test_catalog_rejects_cross_broker_instrument(valid_instrument: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="broker"):
        InstrumentCatalog(
            catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
            version="2026-08-30",
            broker="different-broker",
            instruments=(valid_instrument,),
            observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
        )


def test_instrument_represents_known_but_unsupported_type(
    valid_instrument_data: dict[str, object],
) -> None:
    valid_instrument_data["instrument_type"] = "INVERSE_PERPETUAL"

    assert (
        InstrumentSpec(**valid_instrument_data).instrument_type is InstrumentType.INVERSE_PERPETUAL
    )


def test_unknown_instrument_type_is_a_schema_error(
    valid_instrument_data: dict[str, object],
) -> None:
    valid_instrument_data["instrument_type"] = "MAGIC_PRODUCT"

    with pytest.raises(ValidationError):
        InstrumentSpec(**valid_instrument_data)


def test_catalog_hashes_without_mutation(valid_catalog: InstrumentCatalog) -> None:
    sealed = valid_catalog.with_content_hash()

    assert valid_catalog.content_hash is None
    assert sealed.content_hash == content_sha256(valid_catalog, exclude={"content_hash"})


def test_market_snapshot_rejects_duplicate_quote_symbols(valid_quote: MarketQuote) -> None:
    with pytest.raises(ValidationError, match="unique"):
        MarketSnapshot(**market_data(quotes=(valid_quote, valid_quote)))


@pytest.mark.parametrize("bid,ask", [("0", "100"), ("101", "100")])
def test_market_quote_requires_positive_ordered_book(bid: str, ask: str) -> None:
    with pytest.raises(ValidationError):
        MarketQuote(symbol="BTCUSDT", bid=bid, ask=ask, mark="100")


def test_market_snapshot_normalizes_timestamp_and_hashes(valid_quote: MarketQuote) -> None:
    market = MarketSnapshot(**market_data(quotes=(valid_quote,)))
    sealed = market.with_content_hash()

    assert market.observed_at == datetime(2026, 8, 30, 8, tzinfo=UTC)
    assert market.content_hash is None
    assert sealed.content_hash == content_sha256(market, exclude={"content_hash"})


def test_naive_timestamp_string_is_rejected(valid_quote: MarketQuote) -> None:
    data = market_data(quotes=(valid_quote,))
    data["observed_at"] = "2026-08-30T08:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketSnapshot(**data)


def test_state_contracts_reject_unknown_fields_and_mutation(valid_quote: MarketQuote) -> None:
    data = market_data(quotes=(valid_quote,))
    data["surprise"] = True

    with pytest.raises(ValidationError):
        MarketSnapshot(**data)

    with pytest.raises(ValidationError):
        valid_quote.symbol = "ETHUSDT"  # type: ignore[misc]


def test_position_preserves_signed_quantity_and_normalizes_symbol() -> None:
    position = Position(symbol=" btcusdt ", signed_quantity="-1.25")

    assert position.symbol == "BTCUSDT"
    assert position.signed_quantity == Decimal("-1.25")


def test_account_rejects_duplicate_positions(valid_account_data: dict[str, object]) -> None:
    position = Position(symbol="BTCUSDT", signed_quantity="1")
    valid_account_data["positions"] = (position, position)

    with pytest.raises(ValidationError, match="position symbols"):
        TrustedAccountSnapshot(**valid_account_data)


def test_unknown_order_requires_full_positive_remaining_exposure() -> None:
    order = OpenOrderExposure(
        broker_order_id="order-1",
        intent_id=None,
        symbol="BTCUSDT",
        side="BUY",
        remaining_quantity="0.2",
        reduce_only=False,
        reference_price="100000",
        status="UNKNOWN",
    )

    assert order.remaining_quantity == Decimal("0.2")
    assert order.status is OpenOrderStatus.UNKNOWN


@pytest.mark.parametrize("field", ["remaining_quantity", "reference_price"])
def test_open_order_requires_positive_exposure(field: str) -> None:
    data: dict[str, object] = {
        "broker_order_id": "order-1",
        "intent_id": None,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "remaining_quantity": "0.2",
        "reduce_only": False,
        "reference_price": "100000",
        "status": "NEW",
    }
    data[field] = "0"

    with pytest.raises(ValidationError):
        OpenOrderExposure(**data)


def test_account_rejects_duplicate_broker_order_ids(
    valid_account_data: dict[str, object],
) -> None:
    order = OpenOrderExposure(
        broker_order_id="order-1",
        symbol="BTCUSDT",
        side="SELL",
        remaining_quantity="0.2",
        reduce_only=False,
        reference_price="100000",
        status="PENDING_CANCEL",
    )
    valid_account_data["open_orders"] = (order, order)

    with pytest.raises(ValidationError, match="broker order IDs"):
        TrustedAccountSnapshot(**valid_account_data)


def test_account_sorts_positions_and_orders(valid_account_data: dict[str, object]) -> None:
    valid_account_data["positions"] = (
        Position(symbol="ETHUSDT", signed_quantity="1"),
        Position(symbol="BTCUSDT", signed_quantity="-1"),
    )
    valid_account_data["open_orders"] = (
        OpenOrderExposure(
            broker_order_id="order-2",
            symbol="ETHUSDT",
            side="BUY",
            remaining_quantity="1",
            reduce_only=False,
            reference_price="2000",
            status="PARTIALLY_FILLED",
        ),
        OpenOrderExposure(
            broker_order_id="order-1",
            symbol="BTCUSDT",
            side="SELL",
            remaining_quantity="0.1",
            reduce_only=True,
            reference_price="100000",
            status="NEW",
        ),
    )

    account = TrustedAccountSnapshot(**valid_account_data)

    assert tuple(position.symbol for position in account.positions) == ("BTCUSDT", "ETHUSDT")
    assert tuple(order.broker_order_id for order in account.open_orders) == (
        "order-1",
        "order-2",
    )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("state_version", 0, "greater than 0"),
        ("drawdown_from_peak", Decimal("-0.01"), "greater than or equal to 0"),
    ],
)
def test_account_rejects_invalid_risk_state(
    valid_account_data: dict[str, object], field: str, value: object, match: str
) -> None:
    valid_account_data[field] = value

    with pytest.raises(ValidationError, match=match):
        TrustedAccountSnapshot(**valid_account_data)


def test_account_requires_half_open_pnl_window(valid_account_data: dict[str, object]) -> None:
    valid_account_data["realized_pnl_period_end"] = valid_account_data["realized_pnl_period_start"]

    with pytest.raises(ValidationError, match="period_end"):
        TrustedAccountSnapshot(**valid_account_data)


def test_account_normalizes_utc_and_hashes_without_mutation(
    valid_account_data: dict[str, object],
) -> None:
    valid_account_data["observed_at"] = datetime(
        2026, 8, 30, 16, tzinfo=timezone(timedelta(hours=8))
    )
    account = TrustedAccountSnapshot(**valid_account_data)
    sealed = account.with_content_hash()

    assert account.observed_at == datetime(2026, 8, 30, 8, tzinfo=UTC)
    assert account.content_hash is None
    assert sealed.content_hash == content_sha256(account, exclude={"content_hash"})


def test_account_rejects_bad_hash_unknown_fields_and_mutation(
    valid_account_data: dict[str, object],
) -> None:
    valid_account_data["content_hash"] = "A" * 64
    valid_account_data["surprise"] = True

    with pytest.raises(ValidationError):
        TrustedAccountSnapshot(**valid_account_data)

    valid_account_data.pop("content_hash")
    valid_account_data.pop("surprise")
    account = TrustedAccountSnapshot(**valid_account_data)
    assert account.halt_state is HaltState.NORMAL
    with pytest.raises(ValidationError):
        account.state_version = 8  # type: ignore[misc]
