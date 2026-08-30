from datetime import timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from mnemox_control.canonical import canonical_json_bytes
from mnemox_control.contracts import Decision, Side
from mnemox_control.evaluation import RuleOutcome
from mnemox_control.evaluator import evaluate
from mnemox_control.state import Position
from tests.factories import buy, inputs_for_quantity, valid_inputs

quantities = st.decimals(
    min_value=Decimal("0.001"),
    max_value=Decimal("100"),
    places=3,
    allow_nan=False,
    allow_infinity=False,
)


@given(smaller=quantities, extra=quantities)
def test_more_risk_never_reduces_worst_case_exposure(
    smaller: Decimal, extra: Decimal
) -> None:
    smaller_result = evaluate(**inputs_for_quantity(smaller).as_kwargs())
    larger_result = evaluate(**inputs_for_quantity(smaller + extra).as_kwargs())

    assert larger_result.projected_gross_exposure is not None
    assert smaller_result.projected_gross_exposure is not None
    assert larger_result.projected_gross_exposure >= smaller_result.projected_gross_exposure


@given(pending_quantity=quantities)
def test_adding_pending_risk_never_reduces_exposure(pending_quantity: Decimal) -> None:
    inputs = valid_inputs()
    baseline = evaluate(**inputs.as_kwargs())
    account = inputs.account.model_copy(
        update={
            "open_orders": (buy("BTCUSDT", str(pending_quantity)),),
            "content_hash": None,
        }
    ).with_content_hash()
    with_pending = evaluate(**inputs.replace(account=account).as_kwargs())

    assert baseline.projected_gross_exposure is not None
    assert with_pending.projected_gross_exposure is not None
    assert with_pending.projected_gross_exposure >= baseline.projected_gross_exposure


@given(current=st.decimals(min_value="0.002", max_value="100", places=3))
def test_valid_reduce_only_strictly_reduces_direct_absolute_position(current: Decimal) -> None:
    inputs = valid_inputs()
    reduction = current / Decimal(2)
    account = inputs.account.model_copy(
        update={
            "positions": (Position(symbol="BTCUSDT", signed_quantity=current),),
            "content_hash": None,
        }
    ).with_content_hash()
    intent = inputs.intent.model_copy(
        update={"side": Side.SELL, "quantity": reduction, "reduce_only": True}
    )

    result = evaluate(**inputs.replace(account=account, intent=intent).as_kwargs())

    assert result.proposed_fill_position_quantity is not None
    assert abs(result.proposed_fill_position_quantity) < abs(current)
    assert result.rule("REDUCE_ONLY_VIOLATION").outcome is RuleOutcome.PASS


@given(seconds=st.integers(min_value=1, max_value=20))
def test_bound_time_mutation_changes_result_hash(seconds: int) -> None:
    inputs = valid_inputs()
    first = evaluate(**inputs.as_kwargs())
    second = evaluate(
        **inputs.replace(evaluated_at=inputs.evaluated_at + timedelta(seconds=seconds)).as_kwargs()
    )

    assert first.content_hash != second.content_hash


@given(quantity=quantities)
def test_evaluation_is_byte_deterministic_and_does_not_mutate_inputs(quantity: Decimal) -> None:
    inputs = inputs_for_quantity(quantity)
    snapshots_before = tuple(
        canonical_json_bytes(model)
        for model in (
            inputs.policy,
            inputs.intent,
            inputs.account,
            inputs.market,
            inputs.instruments,
        )
    )

    first = evaluate(**inputs.as_kwargs())
    second = evaluate(**inputs.as_kwargs())

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first.content_hash == second.content_hash
    assert snapshots_before == tuple(
        canonical_json_bytes(model)
        for model in (
            inputs.policy,
            inputs.intent,
            inputs.account,
            inputs.market,
            inputs.instruments,
        )
    )


@given(quantity=st.decimals(min_value="1", max_value="20", places=3))
def test_deny_precedence_is_invariant_when_approval_also_triggers(quantity: Decimal) -> None:
    inputs = inputs_for_quantity(quantity)
    policy = inputs.policy.model_copy(
        update={
            "max_order_notional": Decimal("1"),
            "approval_notional": Decimal("0"),
            "content_hash": None,
        }
    ).with_content_hash()

    result = evaluate(**inputs.replace(policy=policy).as_kwargs())

    assert result.rule("ORDER_NOTIONAL_EXCEEDED").outcome is RuleOutcome.DENY
    assert result.rule("HUMAN_APPROVAL_REQUIRED").outcome is RuleOutcome.ESCALATE
    assert result.decision is Decision.DENY
