from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from mnemox_control.contracts import OrderIntent, PolicyBundle
from mnemox_control.state import (
    InstrumentCatalog,
    InstrumentSpec,
    MarketQuote,
    MarketSnapshot,
    OpenOrderExposure,
    TrustedAccountSnapshot,
)


@dataclass(frozen=True)
class EvaluationInputs:
    policy: PolicyBundle
    intent: OrderIntent
    account: TrustedAccountSnapshot
    market: MarketSnapshot
    instruments: InstrumentCatalog
    evaluated_at: datetime

    def as_kwargs(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "intent": self.intent,
            "account": self.account,
            "market": self.market,
            "instruments": self.instruments,
            "evaluated_at": self.evaluated_at,
        }

    def replace(self, **changes: object) -> Self:
        return dataclasses.replace(self, **changes)


def policy_data() -> dict[str, object]:
    return {
        "policy_id": UUID("11111111-1111-1111-1111-111111111111"),
        "version": "0.2",
        "revision": 1,
        "previous_policy_hash": None,
        "owner_id": "owner-1",
        "account_id": "paper-1",
        "broker": "binance-demo",
        "allowed_symbols": ("BTCUSDT",),
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
        "allow_position_reversal": False,
        "risk_day_start_hour_utc": 0,
        "allowed_weekly_windows": ({"start_minute_utc": 0, "end_minute_utc": 10080},),
        "created_at": datetime(2026, 8, 29, 23, tzinfo=UTC),
        "valid_from": datetime(2026, 8, 30, tzinfo=UTC),
        "expires_at": datetime(2026, 9, 30, tzinfo=UTC),
    }


def buy(symbol: str, quantity: str) -> OpenOrderExposure:
    return OpenOrderExposure(
        broker_order_id=f"buy-{symbol}-{quantity}",
        symbol=symbol,
        side="BUY",
        remaining_quantity=quantity,
        reduce_only=False,
        reference_price="100",
        status="NEW",
    )


def sell(symbol: str, quantity: str) -> OpenOrderExposure:
    return OpenOrderExposure(
        broker_order_id=f"sell-{symbol}-{quantity}",
        symbol=symbol,
        side="SELL",
        remaining_quantity=quantity,
        reduce_only=False,
        reference_price="100",
        status="NEW",
    )


def buy_intent(symbol: str, quantity: str) -> OrderIntent:
    return OrderIntent(
        intent_id=UUID("22222222-2222-2222-2222-222222222222"),
        agent_id="agent-1",
        account_id="paper-1",
        broker="binance-demo",
        symbol=symbol,
        side="BUY",
        order_type="MARKET",
        quantity=quantity,
        reduce_only=False,
        strategy_id="strategy-1",
        reason="deterministic test intent",
        market_data_as_of=datetime(2026, 8, 30, 11, 59, 50, tzinfo=UTC),
        created_at=datetime(2026, 8, 30, 11, 59, 55, tzinfo=UTC),
    )


def catalog_btc(multiplier: str = "1") -> InstrumentCatalog:
    instrument = InstrumentSpec(
        instrument_id="binance:BTCUSDT",
        version="2026-08-30",
        broker="binance-demo",
        symbol="BTCUSDT",
        instrument_type="LINEAR_PERPETUAL",
        position_mode="ONE_WAY",
        allows_short=True,
        base_asset="BTC",
        quote_asset="USDT",
        contract_multiplier=multiplier,
        quantity_step="0.001",
        price_tick="0.1",
        min_quantity="0.001",
        min_notional="5",
    )
    return InstrumentCatalog(
        catalog_id=UUID("33333333-3333-3333-3333-333333333333"),
        version="2026-08-30",
        broker="binance-demo",
        instruments=(instrument,),
        observed_at=datetime(2026, 8, 30, 11, 59, 45, tzinfo=UTC),
    ).with_content_hash()


def market_btc(mark: str = "100") -> MarketSnapshot:
    mark_price = Decimal(mark)
    quote = MarketQuote(
        symbol="BTCUSDT",
        bid=mark_price - Decimal("1"),
        ask=mark_price + Decimal("1"),
        mark=mark_price,
    )
    return MarketSnapshot(
        snapshot_id=UUID("44444444-4444-4444-4444-444444444444"),
        source="binance-market-data",
        quotes=(quote,),
        observed_at=datetime(2026, 8, 30, 11, 59, 50, tzinfo=UTC),
    ).with_content_hash()


def valid_inputs() -> EvaluationInputs:
    policy = PolicyBundle(**policy_data()).with_content_hash()
    account = TrustedAccountSnapshot(
        snapshot_id=UUID("55555555-5555-5555-5555-555555555555"),
        state_version=7,
        source="binance-user-stream",
        account_id="paper-1",
        broker="binance-demo",
        equity="10000",
        cash_balance="10000",
        realized_pnl_today="0",
        realized_pnl_period_start=datetime(2026, 8, 30, tzinfo=UTC),
        realized_pnl_period_end=datetime(2026, 8, 31, tzinfo=UTC),
        drawdown_from_peak="0",
        positions=(),
        open_orders=(),
        halt_state="NORMAL",
        observed_at=datetime(2026, 8, 30, 11, 59, 50, tzinfo=UTC),
    ).with_content_hash()
    return EvaluationInputs(
        policy=policy,
        intent=buy_intent("BTCUSDT", "1"),
        account=account,
        market=market_btc(),
        instruments=catalog_btc(),
        evaluated_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )


def inputs_for_quantity(quantity: Decimal) -> EvaluationInputs:
    inputs = valid_inputs()
    return inputs.replace(intent=inputs.intent.model_copy(update={"quantity": quantity}))
