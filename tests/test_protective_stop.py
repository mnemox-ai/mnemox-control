"""Protocol v0.3: an operator can forbid an agent from opening an unprotected position.

`require_protective_stop` is the dimension that turns "the agent should set a stop" into
"the agent cannot open a position without one". It is a required field with no default,
because every other choice is worse: defaulting it to false would silently give a policy
author who has not heard of it no protection at all, and defaulting it to true would change
what an existing policy means without anyone saying so.

The distance bounds exist because a stop is not protection at any distance. One forty per
cent away does not cap a loss, and one two basis points away is a guaranteed instant fill
and a fee generator.

A reduce-only order never needs a protective stop, so all four rules are new-risk-only: an
order that can only shrink exposure is not the thing this is guarding against.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from mnemox_control import OrderIntent, OrderType, PolicyBundle, ReasonCode, Side
from mnemox_control.evaluator import RULE_ENFORCEMENT, EnforcementClass
from tests.factories import EvaluationInputs, policy_data, valid_inputs


def policy(**changes: object) -> PolicyBundle:
    data = policy_data()
    data.update(changes)
    return PolicyBundle(**data).with_content_hash()


def intent(**changes: object) -> OrderIntent:
    values: dict[str, object] = {
        "intent_id": UUID("22222222-2222-2222-2222-222222222222"),
        "agent_id": "agent-1",
        "account_id": "paper-1",
        "broker": "binance-demo",
        "symbol": "BTCUSDT",
        "side": Side.BUY,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("1"),
        "strategy_id": "strategy-1",
        "reason": "test",
        "market_data_as_of": datetime(2026, 8, 30, 12, tzinfo=UTC),
        "created_at": datetime(2026, 8, 30, 12, tzinfo=UTC),
    }
    values.update(changes)
    return OrderIntent(**values)  # type: ignore[arg-type]


# --- the contract -------------------------------------------------------------------------


def test_the_policy_version_is_now_0_3() -> None:
    assert policy().version == "0.3"


def test_require_protective_stop_has_no_default() -> None:
    """A policy author must decide. Either default would decide it for them, silently."""
    data = policy_data()
    del data["require_protective_stop"]

    with pytest.raises(ValueError, match="require_protective_stop"):
        PolicyBundle(**data)


def test_a_minimum_stop_distance_above_the_maximum_is_refused() -> None:
    with pytest.raises(ValueError, match="min_stop_distance_bps"):
        policy(min_stop_distance_bps=500, max_stop_distance_bps=100)


def test_stop_distance_bounds_are_optional() -> None:
    bundle = policy(min_stop_distance_bps=None, max_stop_distance_bps=None)

    assert bundle.min_stop_distance_bps is None
    assert bundle.max_stop_distance_bps is None


def test_an_entry_may_declare_a_protective_stop() -> None:
    assert intent(protective_stop_price=Decimal("95")).protective_stop_price == Decimal("95")


def test_a_reduce_only_order_may_not_declare_a_protective_stop() -> None:
    """It shrinks exposure, so protecting it is meaningless and would confuse the mapping."""
    with pytest.raises(ValueError, match="reduce-only"):
        intent(reduce_only=True, protective_stop_price=Decimal("95"))


def test_a_stop_order_may_not_declare_a_protective_stop() -> None:
    """A stop protecting a stop is not a shape this protocol has semantics for."""
    with pytest.raises(ValueError, match="protective_stop_price"):
        intent(
            order_type=OrderType.STOP,
            stop_price=Decimal("95"),
            protective_stop_price=Decimal("90"),
        )


def test_the_protective_price_is_distinct_from_the_stop_price() -> None:
    """`stop_price` makes the order a stop; `protective_stop_price` protects an entry."""
    assert "stop_price" in OrderIntent.model_fields
    assert "protective_stop_price" in OrderIntent.model_fields


# --- the rules are new-risk-only ------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        ReasonCode.PROTECTIVE_STOP_REQUIRED,
        ReasonCode.PROTECTIVE_STOP_WRONG_SIDE,
        ReasonCode.PROTECTIVE_STOP_TOO_FAR,
        ReasonCode.PROTECTIVE_STOP_TOO_CLOSE,
    ],
)
def test_every_protective_stop_rule_is_new_risk_only(code: ReasonCode) -> None:
    assert RULE_ENFORCEMENT[code] is EnforcementClass.NEW_RISK_ONLY


# --- evaluation ------------------------------------------------------------------------------


def rule(inputs: EvaluationInputs, code: ReasonCode) -> str:
    """The outcome of one rule. `rules` is a tuple carrying every code exactly once."""

    from mnemox_control import evaluate

    result = evaluate(**inputs.as_kwargs())  # type: ignore[arg-type]
    return next(entry.outcome.value for entry in result.rules if entry.code is code)


def test_an_entry_without_a_stop_is_denied_when_the_policy_requires_one() -> None:
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=True))

    assert rule(inputs, ReasonCode.PROTECTIVE_STOP_REQUIRED) == "DENY"


def test_an_entry_with_a_stop_satisfies_the_requirement() -> None:
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=True))
    protected = inputs.intent.model_copy(update={"protective_stop_price": Decimal("95")})

    assert rule(inputs.replace(intent=protected), ReasonCode.PROTECTIVE_STOP_REQUIRED) == "PASS"


def test_a_policy_that_does_not_require_a_stop_still_allows_an_unprotected_entry() -> None:
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=False))

    assert rule(inputs, ReasonCode.PROTECTIVE_STOP_REQUIRED) == "PASS"


def test_a_long_stop_above_the_reference_price_is_the_wrong_side() -> None:
    """A stop above a long's entry triggers immediately and is not protection."""
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=True))
    wrong = inputs.intent.model_copy(update={"protective_stop_price": Decimal("110")})

    assert rule(inputs.replace(intent=wrong), ReasonCode.PROTECTIVE_STOP_WRONG_SIDE) == "DENY"


def test_a_stop_further_than_the_policy_allows_is_denied() -> None:
    inputs = valid_inputs().replace(
        policy=policy(require_protective_stop=True, max_stop_distance_bps=100)
    )
    far = inputs.intent.model_copy(update={"protective_stop_price": Decimal("50")})

    assert rule(inputs.replace(intent=far), ReasonCode.PROTECTIVE_STOP_TOO_FAR) == "DENY"


def test_a_stop_closer_than_the_policy_allows_is_denied() -> None:
    inputs = valid_inputs().replace(
        policy=policy(require_protective_stop=True, min_stop_distance_bps=100)
    )
    # Reference is the ask, 101. A stop at 100.5 is about 49 bps away.
    close = inputs.intent.model_copy(update={"protective_stop_price": Decimal("100.5")})

    assert rule(inputs.replace(intent=close), ReasonCode.PROTECTIVE_STOP_TOO_CLOSE) == "DENY"


def test_a_stop_exactly_at_the_minimum_distance_is_allowed() -> None:
    """`min` means at least this far, so the boundary itself passes.

    Reference is the ask, 101, so a stop at 99.99 is exactly 100 bps. Picking this value by
    accident is what first surfaced the question; pinning it stops the boundary drifting.
    """
    inputs = valid_inputs().replace(
        policy=policy(require_protective_stop=True, min_stop_distance_bps=100)
    )
    boundary = inputs.intent.model_copy(update={"protective_stop_price": Decimal("99.99")})

    assert rule(inputs.replace(intent=boundary), ReasonCode.PROTECTIVE_STOP_TOO_CLOSE) == "PASS"


def test_a_stop_within_the_declared_band_passes_both_bounds() -> None:
    inputs = valid_inputs().replace(
        policy=policy(
            require_protective_stop=True, min_stop_distance_bps=50, max_stop_distance_bps=1000
        )
    )
    ok = inputs.intent.model_copy(update={"protective_stop_price": Decimal("98")})

    banded = inputs.replace(intent=ok)
    assert rule(banded, ReasonCode.PROTECTIVE_STOP_TOO_FAR) == "PASS"
    assert rule(banded, ReasonCode.PROTECTIVE_STOP_TOO_CLOSE) == "PASS"
    assert rule(banded, ReasonCode.PROTECTIVE_STOP_WRONG_SIDE) == "PASS"


def test_a_stop_exactly_at_the_maximum_distance_is_allowed() -> None:
    """`max` means at most this far, so the boundary itself passes."""
    inputs = valid_inputs().replace(
        policy=policy(require_protective_stop=True, max_stop_distance_bps=100)
    )
    boundary = inputs.intent.model_copy(update={"protective_stop_price": Decimal("99.99")})

    assert rule(inputs.replace(intent=boundary), ReasonCode.PROTECTIVE_STOP_TOO_FAR) == "PASS"


def test_a_wrong_sided_stop_is_not_also_reported_as_a_distance_problem() -> None:
    """Reporting a distance for a stop on the wrong side would describe a meaningless number."""
    inputs = valid_inputs().replace(
        policy=policy(
            require_protective_stop=True, min_stop_distance_bps=50, max_stop_distance_bps=100
        )
    )
    wrong = inputs.intent.model_copy(update={"protective_stop_price": Decimal("500")})
    scenario = inputs.replace(intent=wrong)

    assert rule(scenario, ReasonCode.PROTECTIVE_STOP_WRONG_SIDE) == "DENY"
    assert rule(scenario, ReasonCode.PROTECTIVE_STOP_TOO_FAR) == "PASS"
    assert rule(scenario, ReasonCode.PROTECTIVE_STOP_TOO_CLOSE) == "PASS"


def test_a_short_entry_needs_its_stop_above_the_reference_price() -> None:
    """The mirror of the long case, so the side check is not accidentally one-directional."""
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=True))
    short = inputs.intent.model_copy(
        update={"side": Side.SELL, "protective_stop_price": Decimal("90")}
    )

    assert rule(inputs.replace(intent=short), ReasonCode.PROTECTIVE_STOP_WRONG_SIDE) == "DENY"


def test_a_short_entry_with_a_stop_above_the_reference_price_passes() -> None:
    inputs = valid_inputs().replace(policy=policy(require_protective_stop=True))
    short = inputs.intent.model_copy(
        update={"side": Side.SELL, "protective_stop_price": Decimal("110")}
    )

    assert rule(inputs.replace(intent=short), ReasonCode.PROTECTIVE_STOP_WRONG_SIDE) == "PASS"
