from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import Decision
from mnemox_control.evaluation import (
    EvaluationResult,
    PositionEffect,
    ReasonCode,
    RuleOutcome,
    RuleResult,
)


def pass_rules() -> tuple[RuleResult, ...]:
    return tuple(RuleResult(code=code, outcome="PASS") for code in ReasonCode)


def result_data() -> dict[str, object]:
    return {
        "protocol_version": "0.2",
        "decision": "ALLOW",
        "policy_hash": "a" * 64,
        "intent_hash": "b" * 64,
        "account_snapshot_hash": "c" * 64,
        "market_snapshot_hash": "d" * 64,
        "instrument_catalog_hash": "e" * 64,
        "account_state_version": 7,
        "evaluated_at": datetime(2026, 8, 30, 12, tzinfo=UTC),
        "reference_price": Decimal("101"),
        "order_notional": Decimal("101"),
        "current_position_quantity": Decimal("0"),
        "proposed_fill_position_quantity": Decimal("1"),
        "worst_case_position_quantity": Decimal("1"),
        "worst_case_position_notional": Decimal("101"),
        "projected_gross_exposure": Decimal("101"),
        "projected_leverage": Decimal("0.0101"),
        "position_effect": "OPEN",
        "rules": pass_rules(),
    }


def replace_rule(
    rules: tuple[RuleResult, ...], code: ReasonCode, replacement: RuleResult
) -> tuple[RuleResult, ...]:
    return tuple(replacement if item.code is code else item for item in rules)


def test_reason_code_vocabulary_and_order_are_protocol_fixed() -> None:
    assert len(ReasonCode) == 36
    assert tuple(ReasonCode)[:4] == (
        ReasonCode.UNSEALED_TRUST_INPUT,
        ReasonCode.HASH_MISMATCH,
        ReasonCode.BINDING_MISMATCH,
        ReasonCode.UNSUPPORTED_INSTRUMENT,
    )
    assert tuple(ReasonCode)[-1] is ReasonCode.HUMAN_APPROVAL_REQUIRED


def test_skip_requires_a_deny_dependency() -> None:
    with pytest.raises(ValidationError, match="blocked_by"):
        RuleResult(code="LEVERAGE_EXCEEDED", outcome="SKIP", blocked_by=())


def test_non_skip_forbids_blocked_by() -> None:
    with pytest.raises(ValidationError, match="blocked_by"):
        RuleResult(
            code="LEVERAGE_EXCEEDED",
            outcome="PASS",
            blocked_by=("NON_POSITIVE_EQUITY",),
        )


def test_rule_subjects_and_dependencies_are_normalized() -> None:
    result = RuleResult(
        code="PRICE_COLLAR_EXCEEDED",
        outcome="SKIP",
        blocked_by=("HASH_MISMATCH", "UNSEALED_TRUST_INPUT", "HASH_MISMATCH"),
        subjects=("market", "account", "market"),
    )

    assert result.subjects == ("account", "market")
    assert result.blocked_by == (
        ReasonCode.UNSEALED_TRUST_INPUT,
        ReasonCode.HASH_MISMATCH,
    )


def test_result_requires_every_rule_exactly_once() -> None:
    data = result_data()
    data["rules"] = pass_rules()[:-1]
    with pytest.raises(ValidationError, match="exactly once"):
        EvaluationResult(**data)

    data["rules"] = (*pass_rules()[:-1], pass_rules()[0])
    with pytest.raises(ValidationError, match="exactly once"):
        EvaluationResult(**data)


def test_reordered_rule_construction_has_same_hash() -> None:
    ordered_data = result_data()
    reordered_data = result_data()
    reordered_data["rules"] = tuple(reversed(pass_rules()))

    ordered = EvaluationResult(**ordered_data)
    reordered = EvaluationResult(**reordered_data)

    assert reordered.rules == ordered.rules
    assert ordered.with_content_hash().content_hash == reordered.with_content_hash().content_hash


def test_decision_must_match_worst_rule_outcome() -> None:
    data = result_data()
    data["rules"] = replace_rule(
        pass_rules(),
        ReasonCode.SYMBOL_NOT_ALLOWED,
        RuleResult(code="SYMBOL_NOT_ALLOWED", outcome="DENY"),
    )

    with pytest.raises(ValidationError, match="decision"):
        EvaluationResult(**data)


def test_skip_must_name_a_prior_rule_that_denied() -> None:
    data = result_data()
    rules = replace_rule(
        pass_rules(),
        ReasonCode.LEVERAGE_EXCEEDED,
        RuleResult(
            code="LEVERAGE_EXCEEDED",
            outcome="SKIP",
            blocked_by=("HASH_MISMATCH",),
        ),
    )
    data.update(decision="DENY", rules=rules)

    with pytest.raises(ValidationError, match="prior DENY"):
        EvaluationResult(**data)


def test_skip_cannot_hide_an_otherwise_allow_result() -> None:
    data = result_data()
    rules = replace_rule(
        pass_rules(),
        ReasonCode.LEVERAGE_EXCEEDED,
        RuleResult(
            code="LEVERAGE_EXCEEDED",
            outcome="SKIP",
            blocked_by=("NON_POSITIVE_EQUITY",),
        ),
    )
    data["rules"] = rules

    with pytest.raises(ValidationError):
        EvaluationResult(**data)


def test_nullable_metrics_require_blocking_deny_evidence() -> None:
    data = result_data()
    data["reference_price"] = None

    with pytest.raises(ValidationError, match="undefined metrics"):
        EvaluationResult(**data)

    rules = replace_rule(
        pass_rules(),
        ReasonCode.BINDING_MISMATCH,
        RuleResult(code="BINDING_MISMATCH", outcome="DENY"),
    )
    rules = replace_rule(
        rules,
        ReasonCode.PRICE_COLLAR_EXCEEDED,
        RuleResult(
            code="PRICE_COLLAR_EXCEEDED",
            outcome="SKIP",
            blocked_by=("BINDING_MISMATCH",),
        ),
    )
    data.update(decision="DENY", rules=rules)
    assert EvaluationResult(**data).reference_price is None


def test_result_hashes_without_mutation_and_supports_rule_lookup() -> None:
    result = EvaluationResult(**result_data())
    sealed = result.with_content_hash()

    assert result.content_hash is None
    assert sealed.content_hash == content_sha256(result, exclude={"content_hash"})
    assert result.rule("PRICE_COLLAR_EXCEEDED").outcome is RuleOutcome.PASS
    assert result.position_effect is PositionEffect.OPEN


def test_result_rejects_bad_hash_naive_time_unknown_fields_and_mutation() -> None:
    data = result_data()
    data["policy_hash"] = "A" * 64
    data["evaluated_at"] = "2026-08-30T12:00:00"
    data["broker_order_id"] = "must-not-exist"

    with pytest.raises(ValidationError):
        EvaluationResult(**data)

    result = EvaluationResult(**result_data())
    assert result.decision is Decision.ALLOW
    with pytest.raises(ValidationError):
        result.decision = Decision.DENY  # type: ignore[misc]
