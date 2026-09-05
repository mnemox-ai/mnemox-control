"""Proof-carrying evaluation result contracts for protocol v0.2."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision, StrictFrozenModel

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RuleOutcome(StrEnum):
    PASS = "PASS"
    ESCALATE = "ESCALATE"
    DENY = "DENY"
    SKIP = "SKIP"


class PositionEffect(StrEnum):
    OPEN = "OPEN"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    REVERSE = "REVERSE"


class ReasonCode(StrEnum):
    UNSEALED_TRUST_INPUT = "UNSEALED_TRUST_INPUT"
    HASH_MISMATCH = "HASH_MISMATCH"
    BINDING_MISMATCH = "BINDING_MISMATCH"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    POLICY_NOT_YET_ACTIVE = "POLICY_NOT_YET_ACTIVE"
    POLICY_EXPIRED = "POLICY_EXPIRED"
    ACCOUNT_STATE_FROM_FUTURE = "ACCOUNT_STATE_FROM_FUTURE"
    ACCOUNT_STATE_STALE = "ACCOUNT_STATE_STALE"
    MARKET_STATE_FROM_FUTURE = "MARKET_STATE_FROM_FUTURE"
    MARKET_STATE_STALE = "MARKET_STATE_STALE"
    INSTRUMENT_STATE_FROM_FUTURE = "INSTRUMENT_STATE_FROM_FUTURE"
    INSTRUMENT_STATE_STALE = "INSTRUMENT_STATE_STALE"
    INSTRUMENT_COVERAGE_MISSING = "INSTRUMENT_COVERAGE_MISSING"
    MARKET_COVERAGE_MISSING = "MARKET_COVERAGE_MISSING"
    PNL_WINDOW_MISMATCH = "PNL_WINDOW_MISMATCH"
    OUTSIDE_TRADING_WINDOW = "OUTSIDE_TRADING_WINDOW"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    SOFT_HALT_ACTIVE = "SOFT_HALT_ACTIVE"
    FULL_HALT_ACTIVE = "FULL_HALT_ACTIVE"
    REDUCE_ONLY_MODE = "REDUCE_ONLY_MODE"
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    INVALID_INCREMENT = "INVALID_INCREMENT"
    PRICE_COLLAR_EXCEEDED = "PRICE_COLLAR_EXCEEDED"
    PROTECTIVE_STOP_REQUIRED = "PROTECTIVE_STOP_REQUIRED"
    PROTECTIVE_STOP_WRONG_SIDE = "PROTECTIVE_STOP_WRONG_SIDE"
    PROTECTIVE_STOP_TOO_FAR = "PROTECTIVE_STOP_TOO_FAR"
    PROTECTIVE_STOP_TOO_CLOSE = "PROTECTIVE_STOP_TOO_CLOSE"
    REDUCE_ONLY_VIOLATION = "REDUCE_ONLY_VIOLATION"
    REDUCE_ONLY_UNCERTAIN = "REDUCE_ONLY_UNCERTAIN"
    POSITION_REVERSAL_FORBIDDEN = "POSITION_REVERSAL_FORBIDDEN"
    SHORT_POSITION_FORBIDDEN = "SHORT_POSITION_FORBIDDEN"
    OPEN_ORDER_LIMIT_EXCEEDED = "OPEN_ORDER_LIMIT_EXCEEDED"
    ORDER_QUANTITY_EXCEEDED = "ORDER_QUANTITY_EXCEEDED"
    ORDER_NOTIONAL_EXCEEDED = "ORDER_NOTIONAL_EXCEEDED"
    POSITION_NOTIONAL_EXCEEDED = "POSITION_NOTIONAL_EXCEEDED"
    LEVERAGE_EXCEEDED = "LEVERAGE_EXCEEDED"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    DRAWDOWN_LIMIT_REACHED = "DRAWDOWN_LIMIT_REACHED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


_REASON_INDEX = {code: index for index, code in enumerate(ReasonCode)}


class RuleResult(StrictFrozenModel):
    """Stable outcome and structured evidence for one protocol rule."""

    code: ReasonCode
    outcome: RuleOutcome
    actual: Decimal | str | bool | None = None
    limit: Decimal | str | bool | None = None
    blocked_by: tuple[ReasonCode, ...] = ()
    subjects: tuple[str, ...] = ()

    @field_validator("blocked_by", mode="after")
    @classmethod
    def normalize_dependencies(cls, value: tuple[ReasonCode, ...]) -> tuple[ReasonCode, ...]:
        return tuple(sorted(set(value), key=_REASON_INDEX.__getitem__))

    @field_validator("subjects", mode="before")
    @classmethod
    def normalize_subjects(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
            raise ValueError("subjects must be a collection")
        subjects = {str(item).strip() for item in value}
        if "" in subjects:
            raise ValueError("subjects must not contain blank values")
        return tuple(sorted(subjects))

    @model_validator(mode="after")
    def validate_dependency_shape(self) -> Self:
        if self.outcome is RuleOutcome.SKIP and not self.blocked_by:
            raise ValueError("blocked_by is required for SKIP")
        if self.outcome is not RuleOutcome.SKIP and self.blocked_by:
            raise ValueError("blocked_by is only valid for SKIP")
        return self


class EvaluationResult(StrictFrozenModel):
    """Canonical decision evidence binding every input and protocol rule."""

    protocol_version: Literal["0.2"] = "0.2"
    decision: Decision
    policy_hash: str
    intent_hash: str
    account_snapshot_hash: str
    market_snapshot_hash: str
    instrument_catalog_hash: str
    account_state_version: Annotated[int, Field(gt=0)]
    evaluated_at: datetime
    reference_price: Decimal | None
    order_notional: Decimal | None
    current_position_quantity: Decimal | None
    proposed_fill_position_quantity: Decimal | None
    worst_case_position_quantity: Decimal | None
    worst_case_position_notional: Decimal | None
    projected_gross_exposure: Decimal | None
    projected_leverage: Decimal | None
    position_effect: PositionEffect | None
    rules: tuple[RuleResult, ...]
    content_hash: str | None = None

    @field_validator(
        "policy_hash",
        "intent_hash",
        "account_snapshot_hash",
        "market_snapshot_hash",
        "instrument_catalog_hash",
        "content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HASH_PATTERN.fullmatch(value):
            raise ValueError("hash must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("rules", mode="after")
    @classmethod
    def normalize_rule_order(cls, value: tuple[RuleResult, ...]) -> tuple[RuleResult, ...]:
        return tuple(sorted(value, key=lambda item: _REASON_INDEX[item.code]))

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        rule_by_code = {rule.code: rule for rule in self.rules}
        if len(self.rules) != len(ReasonCode) or set(rule_by_code) != set(ReasonCode):
            raise ValueError("rules must contain every ReasonCode exactly once")

        for rule in self.rules:
            if rule.outcome is not RuleOutcome.SKIP:
                continue
            for dependency in rule.blocked_by:
                dependency_rule = rule_by_code[dependency]
                if (
                    _REASON_INDEX[dependency] >= _REASON_INDEX[rule.code]
                    or dependency_rule.outcome is not RuleOutcome.DENY
                ):
                    raise ValueError("SKIP blocked_by must name a prior DENY rule")

        outcomes = {rule.outcome for rule in self.rules}
        expected_decision = (
            Decision.DENY
            if RuleOutcome.DENY in outcomes
            else Decision.ESCALATE
            if RuleOutcome.ESCALATE in outcomes
            else Decision.ALLOW
        )
        if self.decision is not expected_decision:
            raise ValueError("decision must match the worst rule outcome")

        metrics = (
            self.reference_price,
            self.order_notional,
            self.current_position_quantity,
            self.proposed_fill_position_quantity,
            self.worst_case_position_quantity,
            self.worst_case_position_notional,
            self.projected_gross_exposure,
            self.projected_leverage,
            self.position_effect,
        )
        if any(value is None for value in metrics):
            leverage_only_undefined = (
                self.projected_leverage is None
                and all(value is not None for value in metrics[:-2])
                and self.position_effect is not None
                and rule_by_code[ReasonCode.NON_POSITIVE_EQUITY].actual is True
            )
            has_blocking_evidence = any(
                rule.outcome is RuleOutcome.SKIP and rule.blocked_by for rule in self.rules
            )
            if not leverage_only_undefined and (
                RuleOutcome.DENY not in outcomes or not has_blocking_evidence
            ):
                raise ValueError("undefined metrics require blocking DENY evidence")
        return self

    def rule(self, code: ReasonCode | str) -> RuleResult:
        wanted = ReasonCode(code)
        return next(item for item in self.rules if item.code is wanted)

    def with_content_hash(self) -> Self:
        """Return a sealed result without mutating the unhashed evaluation."""
        digest = content_sha256(self, exclude={"content_hash"})
        return self.model_copy(update={"content_hash": digest})
