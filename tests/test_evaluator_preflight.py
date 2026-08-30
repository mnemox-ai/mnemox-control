from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision, WeeklyWindow
from mnemox_control.evaluation import ReasonCode, RuleOutcome
from mnemox_control.evaluator import evaluate
from mnemox_control.state import InstrumentType, Position
from tests.factories import valid_inputs


def test_evaluates_sealed_fresh_bound_inputs() -> None:
    inputs = valid_inputs()

    result = evaluate(**inputs.as_kwargs())

    assert result.decision is Decision.ALLOW
    assert result.policy_hash == inputs.policy.content_hash
    assert result.intent_hash == content_sha256(inputs.intent)
    assert result.account_snapshot_hash == inputs.account.content_hash
    assert result.market_snapshot_hash == inputs.market.content_hash
    assert result.instrument_catalog_hash == inputs.instruments.content_hash
    assert result.account_state_version == inputs.account.state_version
    assert result.reference_price == Decimal("101")
    assert result.order_notional == Decimal("101")
    assert tuple(rule.code for rule in result.rules) == tuple(ReasonCode)
    assert all(rule.outcome is RuleOutcome.PASS for rule in result.rules)
    assert result.content_hash == content_sha256(result, exclude={"content_hash"})


@pytest.mark.parametrize("trust_input", ["policy", "account", "market", "instruments"])
def test_unsealed_trust_input_denies_and_blocks_dependent_rules(trust_input: str) -> None:
    inputs = valid_inputs()
    unsealed = getattr(inputs, trust_input).model_copy(update={"content_hash": None})
    result = evaluate(**inputs.replace(**{trust_input: unsealed}).as_kwargs())

    assert result.decision is Decision.DENY
    integrity = result.rule("UNSEALED_TRUST_INPUT")
    assert integrity.outcome is RuleOutcome.DENY
    assert integrity.subjects == (trust_input,)
    assert result.rule("ORDER_NOTIONAL_EXCEEDED").outcome is RuleOutcome.SKIP
    assert result.order_notional is None


@pytest.mark.parametrize("trust_input", ["policy", "account", "market", "instruments"])
def test_hash_mismatch_denies_with_aggregate_subject(trust_input: str) -> None:
    inputs = valid_inputs()
    mismatched = getattr(inputs, trust_input).model_copy(update={"content_hash": "f" * 64})
    result = evaluate(**inputs.replace(**{trust_input: mismatched}).as_kwargs())

    assert result.rule("HASH_MISMATCH").outcome is RuleOutcome.DENY
    assert result.rule("HASH_MISMATCH").subjects == (trust_input,)


@pytest.mark.parametrize(
    ("target", "changes", "subject"),
    [
        ("intent", {"account_id": "other"}, "intent.account_id"),
        ("account", {"broker": "other"}, "account.broker"),
        ("instruments", {"broker": "other"}, "instruments.broker"),
    ],
)
def test_binding_mismatch_denies(target: str, changes: dict[str, object], subject: str) -> None:
    inputs = valid_inputs()
    changed = getattr(inputs, target).model_copy(update=changes)
    if target != "intent":
        changed = changed.model_copy(update={"content_hash": None}).with_content_hash()

    result = evaluate(**inputs.replace(**{target: changed}).as_kwargs())

    assert result.rule("BINDING_MISMATCH").outcome is RuleOutcome.DENY
    assert subject in result.rule("BINDING_MISMATCH").subjects


def test_missing_catalog_and_market_coverage_are_distinct_denials() -> None:
    inputs = valid_inputs()
    account = inputs.account.model_copy(
        update={
            "positions": (Position(symbol="ETHUSDT", signed_quantity="2"),),
            "content_hash": None,
        }
    ).with_content_hash()

    result = evaluate(**inputs.replace(account=account).as_kwargs())

    assert result.rule("INSTRUMENT_COVERAGE_MISSING").outcome is RuleOutcome.DENY
    assert result.rule("INSTRUMENT_COVERAGE_MISSING").subjects == ("ETHUSDT",)
    assert result.rule("MARKET_COVERAGE_MISSING").outcome is RuleOutcome.DENY
    assert result.rule("MARKET_COVERAGE_MISSING").subjects == ("ETHUSDT",)
    assert result.projected_gross_exposure is None


def test_known_but_unsupported_instrument_denies_without_wrong_formula() -> None:
    inputs = valid_inputs()
    instrument = inputs.instruments.instruments[0].model_copy(
        update={"instrument_type": InstrumentType.INVERSE_PERPETUAL}
    )
    catalog = inputs.instruments.model_copy(
        update={"instruments": (instrument,), "content_hash": None}
    ).with_content_hash()

    result = evaluate(**inputs.replace(instruments=catalog).as_kwargs())

    assert result.rule("UNSUPPORTED_INSTRUMENT").outcome is RuleOutcome.DENY
    assert result.rule("UNSUPPORTED_INSTRUMENT").subjects == ("BTCUSDT",)
    assert result.order_notional is None


@pytest.mark.parametrize(
    ("target", "rule"),
    [
        ("account", "ACCOUNT_STATE_FROM_FUTURE"),
        ("market", "MARKET_STATE_FROM_FUTURE"),
        ("instruments", "INSTRUMENT_STATE_FROM_FUTURE"),
    ],
)
def test_future_snapshot_is_a_distinct_denial(target: str, rule: str) -> None:
    inputs = valid_inputs()
    changed = getattr(inputs, target).model_copy(
        update={
            "observed_at": inputs.evaluated_at + timedelta(microseconds=1),
            "content_hash": None,
        }
    ).with_content_hash()

    result = evaluate(**inputs.replace(**{target: changed}).as_kwargs())

    assert result.rule(rule).outcome is RuleOutcome.DENY


@pytest.mark.parametrize(
    ("target", "age_field", "rule"),
    [
        ("account", "max_state_age_seconds", "ACCOUNT_STATE_STALE"),
        ("market", "max_market_age_seconds", "MARKET_STATE_STALE"),
        ("instruments", "max_instrument_age_seconds", "INSTRUMENT_STATE_STALE"),
    ],
)
def test_snapshot_age_boundary_is_inclusive(
    target: str, age_field: str, rule: str
) -> None:
    inputs = valid_inputs()
    max_age = getattr(inputs.policy, age_field)
    exact = getattr(inputs, target).model_copy(
        update={
            "observed_at": inputs.evaluated_at - timedelta(seconds=max_age),
            "content_hash": None,
        }
    ).with_content_hash()
    exact_result = evaluate(**inputs.replace(**{target: exact}).as_kwargs())
    assert exact_result.rule(rule).outcome is RuleOutcome.PASS

    stale = exact.model_copy(
        update={
            "observed_at": inputs.evaluated_at
            - timedelta(seconds=max_age, microseconds=1),
            "content_hash": None,
        }
    ).with_content_hash()
    stale_result = evaluate(**inputs.replace(**{target: stale}).as_kwargs())
    assert stale_result.rule(rule).outcome is RuleOutcome.DENY


def test_policy_validity_is_half_open() -> None:
    inputs = valid_inputs()
    at_start = evaluate(**inputs.replace(evaluated_at=inputs.policy.valid_from).as_kwargs())
    at_end = evaluate(**inputs.replace(evaluated_at=inputs.policy.expires_at).as_kwargs())

    assert at_start.rule("POLICY_NOT_YET_ACTIVE").outcome is RuleOutcome.PASS
    assert at_end.rule("POLICY_EXPIRED").outcome is RuleOutcome.DENY


def test_pnl_window_must_match_policy_risk_day() -> None:
    inputs = valid_inputs()
    account = inputs.account.model_copy(
        update={
            "realized_pnl_period_start": datetime(2026, 8, 30, 1, tzinfo=UTC),
            "realized_pnl_period_end": datetime(2026, 8, 31, 1, tzinfo=UTC),
            "content_hash": None,
        }
    ).with_content_hash()

    result = evaluate(**inputs.replace(account=account).as_kwargs())

    assert result.rule("PNL_WINDOW_MISMATCH").outcome is RuleOutcome.DENY


def test_weekly_window_is_half_open() -> None:
    inputs = valid_inputs()
    minute = inputs.evaluated_at.weekday() * 1440 + inputs.evaluated_at.hour * 60
    policy = inputs.policy.model_copy(
        update={
            "allowed_weekly_windows": (
                WeeklyWindow(start_minute_utc=minute - 1, end_minute_utc=minute),
            ),
            "content_hash": None,
        }
    )
    policy = policy.with_content_hash()

    result = evaluate(**inputs.replace(policy=policy).as_kwargs())

    assert result.rule("OUTSIDE_TRADING_WINDOW").outcome is RuleOutcome.DENY
