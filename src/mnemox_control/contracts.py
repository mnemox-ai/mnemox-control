"""Immutable wire contracts for Mnemox Control."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from mnemox_control.canonical import content_sha256

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("value must not be blank")
    return stripped


NonBlankStr = Annotated[str, AfterValidator(_non_blank)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]


class StrictFrozenModel(BaseModel):
    """Base model with strict wire shape and immutable instances."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_datetimes(cls, value: object) -> object:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timestamps must be timezone-aware")
            return value.astimezone(timezone.utc)
        return value


class PolicyBundle(StrictFrozenModel):
    """Owner-defined limits that govern an account for a fixed time window."""

    policy_id: UUID
    version: Literal["0.1"] = "0.1"
    owner_id: NonBlankStr
    account_id: NonBlankStr
    broker: NonBlankStr
    allowed_symbols: tuple[str, ...]
    max_order_notional: NonNegativeDecimal
    max_position_notional: NonNegativeDecimal
    max_leverage: Annotated[Decimal, Field(ge=1)]
    max_daily_loss: NonNegativeDecimal
    max_drawdown: NonNegativeDecimal
    approval_notional: NonNegativeDecimal
    valid_from: datetime
    expires_at: datetime
    created_at: datetime
    content_hash: str | None = None

    @field_validator("allowed_symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
            raise ValueError("allowed_symbols must be a collection")
        symbols = tuple(sorted({_non_blank(str(item)).upper() for item in value}))
        if not symbols:
            raise ValueError("allowed_symbols must not be empty")
        return symbols

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HASH_PATTERN.fullmatch(value):
            raise ValueError("content_hash must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def validate_policy_window(self) -> Self:
        if self.approval_notional > self.max_order_notional:
            raise ValueError("approval_notional cannot exceed max_order_notional")
        if self.valid_from >= self.expires_at:
            raise ValueError("expires_at must be later than valid_from")
        if self.created_at > self.valid_from:
            raise ValueError("created_at cannot be later than valid_from")
        return self

    def with_content_hash(self) -> Self:
        """Return a copy carrying the digest of its unhashed wire content."""
        digest = content_sha256(self, exclude={"content_hash"})
        return self.model_copy(update={"content_hash": digest})


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderIntent(StrictFrozenModel):
    """An order proposed by an agent before policy evaluation."""

    intent_id: UUID
    agent_id: NonBlankStr
    account_id: NonBlankStr
    broker: NonBlankStr
    symbol: NonBlankStr
    side: Side
    order_type: OrderType
    quantity: PositiveDecimal
    limit_price: PositiveDecimal | None = None
    stop_price: PositiveDecimal | None = None
    reduce_only: bool = False
    strategy_id: NonBlankStr
    reason: NonBlankStr
    market_data_as_of: datetime
    created_at: datetime

    @field_validator("symbol", mode="after")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_price_shape(self) -> Self:
        if self.order_type is OrderType.MARKET:
            if self.limit_price is not None or self.stop_price is not None:
                raise ValueError("MARKET orders cannot carry limit_price or stop_price")
        elif self.order_type is OrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError("LIMIT orders require limit_price")
            if self.stop_price is not None:
                raise ValueError("LIMIT orders cannot carry stop_price")
        elif self.order_type is OrderType.STOP:
            if self.stop_price is None:
                raise ValueError("STOP orders require stop_price")
            if self.limit_price is not None:
                raise ValueError("STOP orders cannot carry limit_price")
        return self


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class DecisionReceipt(StrictFrozenModel):
    """Policy decision and evidence references for one order intent."""

    receipt_id: UUID
    intent_id: UUID
    policy_id: UUID
    policy_hash: str
    decision: Decision
    reason_codes: tuple[str, ...] = ()
    evaluated_at: datetime
    order_intent_hash: str
    broker_order_id: str | None = None
    previous_receipt_hash: str | None = None
    content_hash: str | None = None

    @field_validator("reason_codes", mode="before")
    @classmethod
    def normalize_reason_codes(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
            raise ValueError("reason_codes must be a collection")
        return tuple(sorted({_non_blank(str(item)).upper() for item in value}))

    @field_validator(
        "policy_hash",
        "order_intent_hash",
        "previous_receipt_hash",
        "content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HASH_PATTERN.fullmatch(value):
            raise ValueError("hash must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("broker_order_id")
    @classmethod
    def normalize_broker_order_id(cls, value: str | None) -> str | None:
        return _non_blank(value) if value is not None else None

    @model_validator(mode="after")
    def validate_decision_shape(self) -> Self:
        if self.decision in {Decision.DENY, Decision.ESCALATE}:
            if not self.reason_codes:
                raise ValueError("reason_codes are required for DENY or ESCALATE")
            if self.broker_order_id is not None:
                raise ValueError("broker_order_id is forbidden for DENY or ESCALATE")
        return self

    def with_content_hash(self) -> Self:
        """Return a copy carrying the digest of its unhashed wire content."""
        digest = content_sha256(self, exclude={"content_hash"})
        return self.model_copy(update={"content_hash": digest})
