"""Deterministic Policy Decision Point for Mnemox Control protocol v0.2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mnemox_control.calculations import build_exposure_metrics, reference_price
from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision, OrderIntent, PolicyBundle
from mnemox_control.evaluation import EvaluationResult, ReasonCode, RuleOutcome, RuleResult
from mnemox_control.state import (
    InstrumentCatalog,
    InstrumentType,
    MarketSnapshot,
    PositionMode,
    TrustedAccountSnapshot,
)

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
