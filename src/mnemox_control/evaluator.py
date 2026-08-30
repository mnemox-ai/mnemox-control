"""Deterministic Policy Decision Point for Mnemox Control protocol v0.2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from mnemox_control.calculations import (
    build_exposure_metrics,
    is_step_aligned,
    reference_price,
    signed_order_quantity,
)
from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision, OrderIntent, OrderType, PolicyBundle, Side
from mnemox_control.evaluation import EvaluationResult, ReasonCode, RuleOutcome, RuleResult
from mnemox_control.state import (
    HaltState,
    InstrumentCatalog,
    InstrumentType,
    MarketSnapshot,
    PositionMode,
    TrustedAccountSnapshot,
)


class EnforcementClass(StrEnum):
    ALWAYS = "ALWAYS"
    NEW_RISK_ONLY = "NEW_RISK_ONLY"
    NORMAL_PATH_BLOCKER = "NORMAL_PATH_BLOCKER"


_NORMAL_PATH_BLOCKERS = frozenset(
    {ReasonCode.RECONCILE_REQUIRED, ReasonCode.FULL_HALT_ACTIVE}
)
_NEW_RISK_ONLY = frozenset(
    {
        ReasonCode.OUTSIDE_TRADING_WINDOW,
        ReasonCode.SOFT_HALT_ACTIVE,
        ReasonCode.REDUCE_ONLY_MODE,
        ReasonCode.SYMBOL_NOT_ALLOWED,
        ReasonCode.SHORT_POSITION_FORBIDDEN,
        ReasonCode.OPEN_ORDER_LIMIT_EXCEEDED,
        ReasonCode.ORDER_QUANTITY_EXCEEDED,
        ReasonCode.ORDER_NOTIONAL_EXCEEDED,
        ReasonCode.POSITION_NOTIONAL_EXCEEDED,
        ReasonCode.LEVERAGE_EXCEEDED,
        ReasonCode.NON_POSITIVE_EQUITY,
        ReasonCode.DAILY_LOSS_LIMIT_REACHED,
        ReasonCode.DRAWDOWN_LIMIT_REACHED,
        ReasonCode.HUMAN_APPROVAL_REQUIRED,
    }
)
_ALWAYS = frozenset(ReasonCode) - _NORMAL_PATH_BLOCKERS - _NEW_RISK_ONLY
RULE_ENFORCEMENT = {
    code: (
        EnforcementClass.NORMAL_PATH_BLOCKER
        if code in _NORMAL_PATH_BLOCKERS
        else EnforcementClass.NEW_RISK_ONLY
        if code in _NEW_RISK_ONLY
        else EnforcementClass.ALWAYS
    )
    for code in ReasonCode
}
assert set(RULE_ENFORCEMENT) == set(ReasonCode)

_CALCULATION_BLOCKERS = (
    ReasonCode.UNSEALED_TRUST_INPUT,
    ReasonCode.HASH_MISMATCH,
    ReasonCode.BINDING_MISMATCH,
    ReasonCode.UNSUPPORTED_INSTRUMENT,
    ReasonCode.INSTRUMENT_COVERAGE_MISSING,
    ReasonCode.MARKET_COVERAGE_MISSING,
)


def _trusted_hashes(
    *,
    policy: PolicyBundle,
    account: TrustedAccountSnapshot,
    market: MarketSnapshot,
    instruments: InstrumentCatalog,
) -> dict[str, str]:
    return {
        "policy": content_sha256(policy, exclude={"content_hash"}),
        "account": content_sha256(account, exclude={"content_hash"}),
        "market": content_sha256(market, exclude={"content_hash"}),
        "instruments": content_sha256(instruments, exclude={"content_hash"}),
    }


def _expected_pnl_window(policy: PolicyBundle, evaluated_at: datetime) -> tuple[datetime, datetime]:
    start = evaluated_at.replace(
        hour=policy.risk_day_start_hour_utc,
        minute=0,
        second=0,
        microsecond=0,
    )
    if evaluated_at < start:
        start -= timedelta(days=1)
    return start, start + timedelta(days=1)


def _is_inside_weekly_window(policy: PolicyBundle, evaluated_at: datetime) -> bool:
    minute = evaluated_at.weekday() * 1440 + evaluated_at.hour * 60 + evaluated_at.minute
    return any(
        window.start_minute_utc <= minute < window.end_minute_utc
        for window in policy.allowed_weekly_windows
    )


def evaluate(
    *,
    policy: PolicyBundle,
    intent: OrderIntent,
    account: TrustedAccountSnapshot,
    market: MarketSnapshot,
    instruments: InstrumentCatalog,
    evaluated_at: datetime,
) -> EvaluationResult:
    """Evaluate one intent without reading clocks, storage, network, or randomness."""
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("evaluated_at must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(UTC)

    actual_hashes = _trusted_hashes(
        policy=policy,
        account=account,
        market=market,
        instruments=instruments,
    )
    trust_claims: dict[str, str | None] = {
        "policy": policy.content_hash,
        "account": account.content_hash,
        "market": market.content_hash,
        "instruments": instruments.content_hash,
    }
    rules = {code: RuleResult(code=code, outcome=RuleOutcome.PASS) for code in ReasonCode}

    def deny(
        code: ReasonCode,
        *,
        subjects: tuple[str, ...] = (),
        actual: Decimal | str | bool | None = None,
        limit: Decimal | str | bool | None = None,
    ) -> None:
        rules[code] = RuleResult(
            code=code,
            outcome=RuleOutcome.DENY,
            subjects=subjects,
            actual=actual,
            limit=limit,
        )

    unsealed = tuple(
        name for name, claimed_hash in trust_claims.items() if claimed_hash is None
    )
    if unsealed:
        deny(ReasonCode.UNSEALED_TRUST_INPUT, subjects=unsealed)

    mismatched = tuple(
        name
        for name, claimed_hash in trust_claims.items()
        if claimed_hash is not None and claimed_hash != actual_hashes[name]
    )
    if mismatched:
        deny(ReasonCode.HASH_MISMATCH, subjects=mismatched)

    binding_mismatches: list[str] = []
    if intent.account_id != policy.account_id:
        binding_mismatches.append("intent.account_id")
    if account.account_id != policy.account_id:
        binding_mismatches.append("account.account_id")
    if intent.broker != policy.broker:
        binding_mismatches.append("intent.broker")
    if account.broker != policy.broker:
        binding_mismatches.append("account.broker")
    if instruments.broker != policy.broker:
        binding_mismatches.append("instruments.broker")
    if binding_mismatches:
        deny(ReasonCode.BINDING_MISMATCH, subjects=tuple(binding_mismatches))

    needed_symbols = {intent.symbol}
    needed_symbols.update(position.symbol for position in account.positions)
    needed_symbols.update(order.symbol for order in account.open_orders)
    instrument_by_symbol = {item.symbol: item for item in instruments.instruments}
    quote_by_symbol = {quote.symbol: quote for quote in market.quotes}

    missing_instruments = tuple(sorted(needed_symbols - instrument_by_symbol.keys()))
    missing_quotes = tuple(sorted(needed_symbols - quote_by_symbol.keys()))
    unsupported_symbols = tuple(
        sorted(
            symbol
            for symbol in needed_symbols & instrument_by_symbol.keys()
            if instrument_by_symbol[symbol].instrument_type
            not in {InstrumentType.SPOT, InstrumentType.LINEAR_PERPETUAL}
            or instrument_by_symbol[symbol].position_mode is not PositionMode.ONE_WAY
        )
    )
    if unsupported_symbols:
        deny(ReasonCode.UNSUPPORTED_INSTRUMENT, subjects=unsupported_symbols)

    if evaluated_at < policy.valid_from:
        deny(
            ReasonCode.POLICY_NOT_YET_ACTIVE,
            actual=evaluated_at.isoformat(),
            limit=policy.valid_from.isoformat(),
        )
    if evaluated_at >= policy.expires_at:
        deny(
            ReasonCode.POLICY_EXPIRED,
            actual=evaluated_at.isoformat(),
            limit=policy.expires_at.isoformat(),
        )

    temporal_inputs = (
        (
            account.observed_at,
            policy.max_state_age_seconds,
            ReasonCode.ACCOUNT_STATE_FROM_FUTURE,
            ReasonCode.ACCOUNT_STATE_STALE,
        ),
        (
            market.observed_at,
            policy.max_market_age_seconds,
            ReasonCode.MARKET_STATE_FROM_FUTURE,
            ReasonCode.MARKET_STATE_STALE,
        ),
        (
            instruments.observed_at,
            policy.max_instrument_age_seconds,
            ReasonCode.INSTRUMENT_STATE_FROM_FUTURE,
            ReasonCode.INSTRUMENT_STATE_STALE,
        ),
    )
    for observed_at, max_age, future_code, stale_code in temporal_inputs:
        age = evaluated_at - observed_at
        if age < timedelta(0):
            deny(future_code, actual=observed_at.isoformat(), limit=evaluated_at.isoformat())
        elif age > timedelta(seconds=max_age):
            age_seconds = (
                Decimal(age.days * 86400 + age.seconds)
                + Decimal(age.microseconds) / Decimal(1_000_000)
            )
            deny(stale_code, actual=age_seconds, limit=Decimal(max_age))

    if missing_instruments:
        deny(ReasonCode.INSTRUMENT_COVERAGE_MISSING, subjects=missing_instruments)
    if missing_quotes:
        deny(ReasonCode.MARKET_COVERAGE_MISSING, subjects=missing_quotes)

    expected_pnl_start, expected_pnl_end = _expected_pnl_window(policy, evaluated_at)
    if (
        account.realized_pnl_period_start != expected_pnl_start
        or account.realized_pnl_period_end != expected_pnl_end
        or not (
            account.realized_pnl_period_start
            <= evaluated_at
            < account.realized_pnl_period_end
        )
    ):
        deny(
            ReasonCode.PNL_WINDOW_MISMATCH,
            subjects=("account.realized_pnl_period",),
        )

    if not _is_inside_weekly_window(policy, evaluated_at):
        deny(ReasonCode.OUTSIDE_TRADING_WINDOW)

    if account.halt_state is HaltState.RECONCILE_REQUIRED:
        deny(ReasonCode.RECONCILE_REQUIRED, actual=account.halt_state.value)
    if account.halt_state is HaltState.SOFT_HALT:
        deny(ReasonCode.SOFT_HALT_ACTIVE, actual=account.halt_state.value)
    if account.halt_state is HaltState.FULL_HALT:
        deny(ReasonCode.FULL_HALT_ACTIVE, actual=account.halt_state.value)
    if account.halt_state is HaltState.REDUCE_ONLY:
        deny(ReasonCode.REDUCE_ONLY_MODE, actual=account.halt_state.value)
    if intent.symbol not in policy.allowed_symbols:
        deny(ReasonCode.SYMBOL_NOT_ALLOWED, subjects=(intent.symbol,))

    calculation_blockers = tuple(
        code for code in _CALCULATION_BLOCKERS if rules[code].outcome is RuleOutcome.DENY
    )
    if calculation_blockers:
        for code in tuple(ReasonCode)[21:]:
            rules[code] = RuleResult(
                code=code,
                outcome=RuleOutcome.SKIP,
                blocked_by=calculation_blockers,
            )
        reference = None
        order_notional = None
        current_quantity = None
        proposed_fill = None
        worst_quantity = None
        worst_notional = None
        gross_exposure = None
        leverage = None
        position_effect = None
    else:
        quote = quote_by_symbol[intent.symbol]
        instrument = instrument_by_symbol[intent.symbol]
        reference = reference_price(intent, quote)
        order_notional = intent.quantity * reference * instrument.contract_multiplier
        metrics = build_exposure_metrics(
            current={position.symbol: position.signed_quantity for position in account.positions},
            pending=account.open_orders,
            proposed=intent,
            catalog=instruments,
            market=market,
            equity=account.equity,
        )
        current_quantity = metrics.current_position_quantity
        proposed_fill = metrics.proposed_fill_position_quantity
        worst_quantity = metrics.worst_case_position_quantities[intent.symbol]
        worst_notional = metrics.worst_case_position_notional
        gross_exposure = metrics.projected_gross_exposure
        leverage = metrics.projected_leverage
        position_effect = metrics.position_effect

        signed_quantity = signed_order_quantity(intent)
        valid_strict_reducer = (
            intent.reduce_only
            and current_quantity != 0
            and (signed_quantity > 0) != (current_quantity > 0)
            and abs(proposed_fill) < abs(current_quantity)
            and (
                proposed_fill == 0
                or (proposed_fill > 0) == (current_quantity > 0)
            )
        )

        def set_violation(
            code: ReasonCode,
            condition: bool,
            *,
            actual: Decimal | str | bool | None = None,
            limit: Decimal | str | bool | None = None,
            subjects: tuple[str, ...] = (),
            escalation: bool = False,
        ) -> None:
            if not condition:
                return
            if (
                valid_strict_reducer
                and RULE_ENFORCEMENT[code] is EnforcementClass.NEW_RISK_ONLY
            ):
                rules[code] = RuleResult(
                    code=code,
                    outcome=RuleOutcome.PASS,
                    actual=actual,
                    limit=limit,
                    subjects=subjects,
                )
                return
            rules[code] = RuleResult(
                code=code,
                outcome=RuleOutcome.ESCALATE if escalation else RuleOutcome.DENY,
                actual=actual,
                limit=limit,
                subjects=subjects,
            )

        # Re-apply the data-driven exemptions to pre-calculation new-risk rules.
        for code in (
            ReasonCode.OUTSIDE_TRADING_WINDOW,
            ReasonCode.SOFT_HALT_ACTIVE,
            ReasonCode.REDUCE_ONLY_MODE,
            ReasonCode.SYMBOL_NOT_ALLOWED,
        ):
            if (
                valid_strict_reducer
                and rules[code].outcome is RuleOutcome.DENY
                and RULE_ENFORCEMENT[code] is EnforcementClass.NEW_RISK_ONLY
            ):
                rules[code] = RuleResult(code=code, outcome=RuleOutcome.PASS)

        declared_price = (
            intent.limit_price
            if intent.order_type is OrderType.LIMIT
            else intent.stop_price
            if intent.order_type is OrderType.STOP
            else None
        )
        invalid_increment_subjects: list[str] = []
        if not is_step_aligned(intent.quantity, instrument.quantity_step):
            invalid_increment_subjects.append("intent.quantity_step")
        if declared_price is not None and not is_step_aligned(
            declared_price, instrument.price_tick
        ):
            invalid_increment_subjects.append("intent.price_tick")
        if intent.quantity < instrument.min_quantity:
            invalid_increment_subjects.append("intent.min_quantity")
        if order_notional < instrument.min_notional:
            invalid_increment_subjects.append("intent.min_notional")
        set_violation(
            ReasonCode.INVALID_INCREMENT,
            bool(invalid_increment_subjects),
            subjects=tuple(invalid_increment_subjects),
        )

        mark = quote.mark
        deviation_bps = (
            (reference - mark) / mark * Decimal(10000)
            if intent.side is Side.BUY and reference > mark
            else (mark - reference) / mark * Decimal(10000)
            if intent.side is Side.SELL and reference < mark
            else Decimal(0)
        )
        set_violation(
            ReasonCode.PRICE_COLLAR_EXCEEDED,
            deviation_bps > policy.max_price_deviation_bps,
            actual=deviation_bps,
            limit=policy.max_price_deviation_bps,
        )
        set_violation(
            ReasonCode.REDUCE_ONLY_VIOLATION,
            intent.reduce_only and not valid_strict_reducer,
            actual=position_effect.value,
        )
        set_violation(
            ReasonCode.REDUCE_ONLY_UNCERTAIN,
            intent.reduce_only and any(
                order.symbol == intent.symbol for order in account.open_orders
            ),
            subjects=(intent.symbol,),
        )
        set_violation(
            ReasonCode.POSITION_REVERSAL_FORBIDDEN,
            position_effect.value == "REVERSE" and not policy.allow_position_reversal,
            actual=position_effect.value,
            limit=policy.allow_position_reversal,
        )
        set_violation(
            ReasonCode.SHORT_POSITION_FORBIDDEN,
            proposed_fill < 0 and not instrument.allows_short,
            actual=proposed_fill,
            limit=instrument.allows_short,
        )
        proposed_open_orders = len(account.open_orders) + 1
        set_violation(
            ReasonCode.OPEN_ORDER_LIMIT_EXCEEDED,
            proposed_open_orders > policy.max_open_orders,
            actual=Decimal(proposed_open_orders),
            limit=Decimal(policy.max_open_orders),
        )
        set_violation(
            ReasonCode.ORDER_QUANTITY_EXCEEDED,
            policy.max_order_quantity is not None
            and intent.quantity > policy.max_order_quantity,
            actual=intent.quantity,
            limit=policy.max_order_quantity,
        )
        set_violation(
            ReasonCode.ORDER_NOTIONAL_EXCEEDED,
            order_notional > policy.max_order_notional,
            actual=order_notional,
            limit=policy.max_order_notional,
        )
        set_violation(
            ReasonCode.POSITION_NOTIONAL_EXCEEDED,
            worst_notional > policy.max_position_notional,
            actual=worst_notional,
            limit=policy.max_position_notional,
        )
        set_violation(
            ReasonCode.LEVERAGE_EXCEEDED,
            leverage is not None and leverage > policy.max_leverage,
            actual=leverage,
            limit=policy.max_leverage,
        )
        set_violation(
            ReasonCode.NON_POSITIVE_EQUITY,
            account.equity <= 0,
            actual=account.equity <= 0,
            limit=False,
        )
        set_violation(
            ReasonCode.DAILY_LOSS_LIMIT_REACHED,
            account.realized_pnl_today <= -policy.max_daily_loss,
            actual=account.realized_pnl_today,
            limit=-policy.max_daily_loss,
        )
        set_violation(
            ReasonCode.DRAWDOWN_LIMIT_REACHED,
            account.drawdown_from_peak >= policy.max_drawdown,
            actual=account.drawdown_from_peak,
            limit=policy.max_drawdown,
        )
        set_violation(
            ReasonCode.HUMAN_APPROVAL_REQUIRED,
            order_notional >= policy.approval_notional,
            actual=order_notional,
            limit=policy.approval_notional,
            escalation=True,
        )

    ordered_rules = tuple(rules[code] for code in ReasonCode)
    outcomes = {rule.outcome for rule in ordered_rules}
    decision = (
        Decision.DENY
        if RuleOutcome.DENY in outcomes
        else Decision.ESCALATE
        if RuleOutcome.ESCALATE in outcomes
        else Decision.ALLOW
    )
    return EvaluationResult(
        decision=decision,
        policy_hash=actual_hashes["policy"],
        intent_hash=content_sha256(intent),
        account_snapshot_hash=actual_hashes["account"],
        market_snapshot_hash=actual_hashes["market"],
        instrument_catalog_hash=actual_hashes["instruments"],
        account_state_version=account.state_version,
        evaluated_at=evaluated_at,
        reference_price=reference,
        order_notional=order_notional,
        current_position_quantity=current_quantity,
        proposed_fill_position_quantity=proposed_fill,
        worst_case_position_quantity=worst_quantity,
        worst_case_position_notional=worst_notional,
        projected_gross_exposure=gross_exposure,
        projected_leverage=leverage,
        position_effect=position_effect,
        rules=ordered_rules,
    ).with_content_hash()
