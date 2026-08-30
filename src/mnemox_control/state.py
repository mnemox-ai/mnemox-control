"""Sealed instrument and market-state contracts for policy evaluation."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import NonBlankStr, PositiveDecimal, StrictFrozenModel

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _validated_hash(value: str | None) -> str | None:
    if value is not None and not _HASH_PATTERN.fullmatch(value):
        raise ValueError("content_hash must be 64 lowercase hexadecimal characters")
    return value


class InstrumentType(StrEnum):
    """Complete instrument vocabulary recognized by the v0.2 wire protocol."""

    SPOT = "SPOT"
    LINEAR_PERPETUAL = "LINEAR_PERPETUAL"
    INVERSE_PERPETUAL = "INVERSE_PERPETUAL"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class PositionMode(StrEnum):
    """Position-accounting modes recognized by the v0.2 wire protocol."""

    ONE_WAY = "ONE_WAY"
    HEDGE = "HEDGE"


class InstrumentSpec(StrictFrozenModel):
    """Versioned broker facts needed to value and validate one instrument."""

    instrument_id: NonBlankStr
    version: NonBlankStr
    broker: NonBlankStr
    symbol: NonBlankStr
    instrument_type: InstrumentType
    position_mode: PositionMode
    allows_short: bool
    base_asset: NonBlankStr
    quote_asset: NonBlankStr
    contract_multiplier: PositiveDecimal
    quantity_step: PositiveDecimal
    price_tick: PositiveDecimal
    min_quantity: PositiveDecimal
    min_notional: PositiveDecimal

    @field_validator("symbol", "base_asset", "quote_asset", mode="after")
    @classmethod
    def uppercase_market_identifier(cls, value: str) -> str:
        return value.upper()


class InstrumentCatalog(StrictFrozenModel):
    """Immutable, broker-bound collection of versioned instrument facts."""

    catalog_id: UUID
    version: NonBlankStr
    broker: NonBlankStr
    instruments: Annotated[tuple[InstrumentSpec, ...], Field(min_length=1)]
    observed_at: datetime
    content_hash: str | None = None

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str | None) -> str | None:
        return _validated_hash(value)

    @model_validator(mode="after")
    def validate_catalog_identity(self) -> Self:
        instrument_ids = [item.instrument_id for item in self.instruments]
        symbols = [item.symbol for item in self.instruments]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("instrument IDs must be unique")
        if len(symbols) != len(set(symbols)):
            raise ValueError("instrument symbols must be unique")
        if any(item.broker != self.broker for item in self.instruments):
            raise ValueError("every instrument broker must match the catalog broker")
        return self

    def with_content_hash(self) -> Self:
        """Return a sealed copy without mutating the caller's catalog."""
        digest = content_sha256(self, exclude={"content_hash"})
        return self.model_copy(update={"content_hash": digest})


class MarketQuote(StrictFrozenModel):
    """One complete positive top-of-book and mark-price observation."""

    symbol: NonBlankStr
    bid: PositiveDecimal
    ask: PositiveDecimal
    mark: PositiveDecimal

    @field_validator("symbol", mode="after")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_ordered_book(self) -> Self:
        if self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        return self


class MarketSnapshot(StrictFrozenModel):
    """Immutable set of quotes sufficient for account-wide valuation."""

    snapshot_id: UUID
    source: NonBlankStr
    quotes: Annotated[tuple[MarketQuote, ...], Field(min_length=1)]
    observed_at: datetime
    content_hash: str | None = None

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str | None) -> str | None:
        return _validated_hash(value)

    @model_validator(mode="after")
    def validate_quote_identity(self) -> Self:
        symbols = [quote.symbol for quote in self.quotes]
        if len(symbols) != len(set(symbols)):
            raise ValueError("quote symbols must be unique")
        return self

    def with_content_hash(self) -> Self:
        """Return a sealed copy without mutating the caller's snapshot."""
        digest = content_sha256(self, exclude={"content_hash"})
        return self.model_copy(update={"content_hash": digest})
