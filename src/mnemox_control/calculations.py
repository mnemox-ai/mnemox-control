"""Pure Decimal calculations for signed positions and conservative exposure."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from mnemox_control.contracts import OrderIntent, OrderType, Side
from mnemox_control.evaluation import PositionEffect
from mnemox_control.state import InstrumentCatalog, MarketQuote, MarketSnapshot, OpenOrderExposure


class CalculationCoverageError(ValueError):
    """Raised when account-wide exposure cannot be valued without dropping symbols."""

    def __init__(
        self,
        *,
        missing_instruments: tuple[str, ...],
        missing_quotes: tuple[str, ...],
    ) -> None:
        self.missing_instruments = missing_instruments
        self.missing_quotes = missing_quotes
        details = []
        if missing_instruments:
            details.append(f"missing instruments: {', '.join(missing_instruments)}")
        if missing_quotes:
            details.append(f"missing quotes: {', '.join(missing_quotes)}")
        super().__init__("; ".join(details))


@dataclass(frozen=True)
class ExposureMetrics:
    current_position_quantity: Decimal
    proposed_fill_position_quantity: Decimal
    worst_case_position_quantities: Mapping[str, Decimal]
    worst_case_position_notional: Decimal
    projected_gross_exposure: Decimal
    projected_leverage: Decimal | None
    position_effect: PositionEffect


def signed_order_quantity(intent: OrderIntent) -> Decimal:
    """Translate a side and unsigned order quantity into position delta."""
    return intent.quantity if intent.side == Side.BUY else -intent.quantity


def classify_position_effect(current: Decimal, proposed: Decimal) -> PositionEffect:
    """Classify the direct signed-position transition caused by an intent."""
    if current == proposed:
        raise ValueError("position is unchanged")
    if current == 0:
        return PositionEffect.OPEN
    if proposed == 0:
        return PositionEffect.CLOSE
    if (current > 0) != (proposed > 0):
        return PositionEffect.REVERSE
    if abs(proposed) > abs(current):
        return PositionEffect.INCREASE
    return PositionEffect.REDUCE


def reference_price(intent: OrderIntent, quote: MarketQuote) -> Decimal:
    """Select the protocol-defined executable price for the proposed order."""
    if intent.order_type == OrderType.MARKET:
        return quote.ask if intent.side == Side.BUY else quote.bid
    if intent.order_type == OrderType.LIMIT:
        if intent.limit_price is None:  # Defensive against unchecked model_copy use.
            raise ValueError("LIMIT order is missing limit_price")
        return intent.limit_price
    if intent.stop_price is None:  # Defensive against unchecked model_copy use.
        raise ValueError("STOP order is missing stop_price")
    return intent.stop_price


def is_step_aligned(value: Decimal, step: Decimal) -> bool:
    """Check exact Decimal alignment without float conversion or rounding."""
    if step <= 0:
        raise ValueError("step must be positive")
    return value % step == 0


def build_exposure_metrics(
    *,
    current: Mapping[str, Decimal],
    pending: tuple[OpenOrderExposure, ...],
    proposed: OrderIntent,
    catalog: InstrumentCatalog,
    market: MarketSnapshot,
    equity: Decimal,
) -> ExposureMetrics:
    """Build a non-netted account-wide exposure envelope for one intent."""
    current_by_symbol = {symbol.upper(): quantity for symbol, quantity in current.items()}
    instruments = {instrument.symbol: instrument for instrument in catalog.instruments}
    quotes = {quote.symbol: quote for quote in market.quotes}
    symbols = set(current_by_symbol)
    symbols.update(order.symbol for order in pending)
    symbols.add(proposed.symbol)

    missing_instruments = tuple(sorted(symbols - instruments.keys()))
    missing_quotes = tuple(sorted(symbols - quotes.keys()))
    if missing_instruments or missing_quotes:
        raise CalculationCoverageError(
            missing_instruments=missing_instruments,
            missing_quotes=missing_quotes,
        )

    target_current = current_by_symbol.get(proposed.symbol, Decimal(0))
    proposed_fill = target_current + signed_order_quantity(proposed)
    effect = classify_position_effect(target_current, proposed_fill)

    worst_quantities: dict[str, Decimal] = {}
    notionals: dict[str, Decimal] = {}
    for symbol in sorted(symbols):
        current_quantity = current_by_symbol.get(symbol, Decimal(0))
        upper_quantity = current_quantity
        lower_quantity = current_quantity
        conservative_price = quotes[symbol].mark

        for order in pending:
            if order.symbol != symbol or order.reduce_only:
                continue
            conservative_price = max(
                conservative_price,
                quotes[symbol].mark,
                order.reference_price,
            )
            if order.side == Side.BUY:
                upper_quantity += order.remaining_quantity
            else:
                lower_quantity -= order.remaining_quantity

        if proposed.symbol == symbol and not proposed.reduce_only:
            proposed_reference = reference_price(proposed, quotes[symbol])
            conservative_price = max(conservative_price, quotes[symbol].mark, proposed_reference)
            if proposed.side == Side.BUY:
                upper_quantity += proposed.quantity
            else:
                lower_quantity -= proposed.quantity

        worst_quantity = (
            upper_quantity if abs(upper_quantity) >= abs(lower_quantity) else lower_quantity
        )
        worst_quantities[symbol] = worst_quantity
        notionals[symbol] = (
            abs(worst_quantity) * conservative_price * instruments[symbol].contract_multiplier
        )

    gross_exposure = sum(notionals.values(), start=Decimal(0))
    return ExposureMetrics(
        current_position_quantity=target_current,
        proposed_fill_position_quantity=proposed_fill,
        worst_case_position_quantities=MappingProxyType(worst_quantities),
        worst_case_position_notional=notionals[proposed.symbol],
        projected_gross_exposure=gross_exposure,
        projected_leverage=gross_exposure / equity if equity > 0 else None,
        position_effect=effect,
    )
