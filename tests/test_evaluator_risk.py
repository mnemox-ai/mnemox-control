from decimal import Decimal

import pytest

from mnemox_control.contracts import Decision, Side, WeeklyWindow
from mnemox_control.evaluation import PositionEffect, ReasonCode, RuleOutcome
from mnemox_control.evaluator import RULE_ENFORCEMENT, EnforcementClass, evaluate
from mnemox_control.state import HaltState, InstrumentType, Position
from tests.factories import buy, valid_inputs


def sealed_policy(inputs: object, **changes: object) -> object:
    policy = inputs.policy.model_copy(update={**changes, "content_hash": None})
    return policy.with_content_hash()


def sealed_account(inputs: object, **changes: object) -> object:
    account = inputs.account.model_copy(update={**changes, "content_hash": None})
    return account.with_content_hash()


def strict_reducer_inputs() -> object:
    inputs = valid_inputs()
    account = sealed_account(
        inputs,
        positions=(Position(symbol="BTCUSDT", signed_quantity="2"),),
    )
    intent = inputs.intent.model_copy(
        update={"side": Side.SELL, "quantity": Decimal("1"), "reduce_only": True}
    )
    return inputs.replace(account=account, intent=intent)


def test_every_reason_has_one_explicit_enforcement_class() -> None:
    assert set(RULE_ENFORCEMENT) == set(ReasonCode)
    assert all(isinstance(value, EnforcementClass) for value in RULE_ENFORCEMENT.values())


def test_deny_outranks_human_approval() -> None:
    inputs = valid_inputs()
    policy = sealed_policy(
        inputs,
        max_order_notional=Decimal("50"),
        approval_notional=Decimal("25"),
    )
    result = evaluate(**inputs.replace(policy=policy).as_kwargs())

    assert result.decision is Decision.DENY
    assert result.rule("ORDER_NOTIONAL_EXCEEDED").outcome is RuleOutcome.DENY
    assert result.rule("HUMAN_APPROVAL_REQUIRED").outcome is RuleOutcome.ESCALATE


def test_scalar_maximum_boundaries_are_inclusive() -> None:
    inputs = valid_inputs()
    policy = sealed_policy(
        inputs,
        max_order_quantity=Decimal("1"),
        max_order_notional=Decimal("101"),
        max_position_notional=Decimal("101"),
        max_leverage=Decimal("0.0101"),
        max_open_orders=1,
        approval_notional=Decimal("1000"),
    )
    result = evaluate(**inputs.replace(policy=policy).as_kwargs())

    assert result.decision is Decision.ALLOW
    for code in (
        "OPEN_ORDER_LIMIT_EXCEEDED",
        "ORDER_QUANTITY_EXCEEDED",
        "ORDER_NOTIONAL_EXCEEDED",
        "POSITION_NOTIONAL_EXCEEDED",
        "LEVERAGE_EXCEEDED",
    ):
        assert result.rule(code).outcome is RuleOutcome.PASS


@pytest.mark.parametrize(
    ("account_changes", "rule"),
    [
        ({"realized_pnl_today": Decimal("-100")}, "DAILY_LOSS_LIMIT_REACHED"),
        ({"drawdown_from_peak": Decimal("500")}, "DRAWDOWN_LIMIT_REACHED"),
    ],
)
def test_loss_boundaries_deny_at_threshold(account_changes: dict[str, object], rule: str) -> None:
    inputs = valid_inputs()
    account = sealed_account(inputs, **account_changes)

    result = evaluate(**inputs.replace(account=account).as_kwargs())

    assert result.rule(rule).outcome is RuleOutcome.DENY


def test_valid_reduce_only_is_monotonic_and_exempts_new_risk_limits() -> None:
    inputs = strict_reducer_inputs()
    policy = sealed_policy(
        inputs,
        allowed_symbols=("ETHUSDT",),
        max_open_orders=0,
        max_order_quantity=Decimal("0.5"),
        max_order_notional=Decimal("50"),
        max_position_notional=Decimal("50"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        approval_notional=Decimal("0"),
    )
    account = sealed_account(
        inputs,
        halt_state=HaltState.SOFT_HALT,
        equity=Decimal("50"),
        realized_pnl_today=Decimal("-100"),
        drawdown_from_peak=Decimal("500"),
    )
    result = evaluate(**inputs.replace(policy=policy, account=account).as_kwargs())

    assert result.position_effect is PositionEffect.REDUCE
    for code in (
        "SOFT_HALT_ACTIVE",
        "SYMBOL_NOT_ALLOWED",
        "OPEN_ORDER_LIMIT_EXCEEDED",
        "ORDER_QUANTITY_EXCEEDED",
        "ORDER_NOTIONAL_EXCEEDED",
        "POSITION_NOTIONAL_EXCEEDED",
        "LEVERAGE_EXCEEDED",
        "DAILY_LOSS_LIMIT_REACHED",
        "DRAWDOWN_LIMIT_REACHED",
        "HUMAN_APPROVAL_REQUIRED",
    ):
        assert result.rule(code).outcome is RuleOutcome.PASS


@pytest.mark.parametrize("halt_state", [HaltState.FULL_HALT, HaltState.RECONCILE_REQUIRED])
def test_normal_api_never_bypasses_full_halt_or_reconcile(halt_state: HaltState) -> None:
    inputs = strict_reducer_inputs()
    account = sealed_account(inputs, halt_state=halt_state)

    result = evaluate(**inputs.replace(account=account).as_kwargs())

    expected = "FULL_HALT_ACTIVE" if halt_state is HaltState.FULL_HALT else "RECONCILE_REQUIRED"
    assert result.rule(expected).outcome is RuleOutcome.DENY


@pytest.mark.parametrize(
    ("current", "quantity"),
    [("0", "1"), ("1", "2"), ("1", "1.1")],
)
def test_reduce_only_must_strictly_reduce_without_crossing_zero(
    current: str, quantity: str
) -> None:
    inputs = valid_inputs()
    account = sealed_account(
        inputs,
        positions=(Position(symbol="BTCUSDT", signed_quantity=current),),
    )
    intent = inputs.intent.model_copy(
        update={"side": Side.SELL, "quantity": Decimal(quantity), "reduce_only": True}
    )

    result = evaluate(**inputs.replace(account=account, intent=intent).as_kwargs())

    assert result.rule("REDUCE_ONLY_VIOLATION").outcome is RuleOutcome.DENY


def test_reduce_only_with_pending_target_order_is_uncertain() -> None:
    inputs = strict_reducer_inputs()
    account = sealed_account(inputs, open_orders=(buy("BTCUSDT", "0.1"),))

    result = evaluate(**inputs.replace(account=account).as_kwargs())

    assert result.rule("REDUCE_ONLY_UNCERTAIN").outcome is RuleOutcome.DENY


def test_position_reversal_obeys_policy() -> None:
    inputs = valid_inputs()
    account = sealed_account(
        inputs,
        positions=(Position(symbol="BTCUSDT", signed_quantity="1"),),
    )
    intent = inputs.intent.model_copy(update={"side": Side.SELL, "quantity": Decimal("2")})
    denied = evaluate(**inputs.replace(account=account, intent=intent).as_kwargs())
    assert denied.rule("POSITION_REVERSAL_FORBIDDEN").outcome is RuleOutcome.DENY

    policy = sealed_policy(inputs, allow_position_reversal=True)
    allowed = evaluate(**inputs.replace(policy=policy, account=account, intent=intent).as_kwargs())
    assert allowed.rule("POSITION_REVERSAL_FORBIDDEN").outcome is RuleOutcome.PASS


def test_short_forbidden_spot_instrument_denies() -> None:
    inputs = valid_inputs()
    instrument = inputs.instruments.instruments[0].model_copy(
        update={"instrument_type": InstrumentType.SPOT, "allows_short": False}
    )
    catalog = inputs.instruments.model_copy(
        update={"instruments": (instrument,), "content_hash": None}
    ).with_content_hash()
    intent = inputs.intent.model_copy(update={"side": Side.SELL})

    result = evaluate(**inputs.replace(instruments=catalog, intent=intent).as_kwargs())

    assert result.rule("SHORT_POSITION_FORBIDDEN").outcome is RuleOutcome.DENY


def test_increment_and_price_collar_still_deny_reducer() -> None:
    inputs = strict_reducer_inputs()
    intent = inputs.intent.model_copy(update={"quantity": Decimal("1.0001")})
    increment = evaluate(**inputs.replace(intent=intent).as_kwargs())
    assert increment.rule("INVALID_INCREMENT").outcome is RuleOutcome.DENY

    policy = sealed_policy(inputs, max_price_deviation_bps=Decimal("0"))
    collar = evaluate(**inputs.replace(policy=policy).as_kwargs())
    assert collar.rule("PRICE_COLLAR_EXCEEDED").outcome is RuleOutcome.DENY


def test_human_approval_threshold_is_inclusive() -> None:
    inputs = valid_inputs()
    policy = sealed_policy(inputs, approval_notional=Decimal("101"))

    result = evaluate(**inputs.replace(policy=policy).as_kwargs())

    assert result.decision is Decision.ESCALATE
    assert result.rule("HUMAN_APPROVAL_REQUIRED").outcome is RuleOutcome.ESCALATE


def test_non_positive_equity_denies_new_risk_but_allows_strict_reducer() -> None:
    new_risk = valid_inputs()
    insolvent = sealed_account(new_risk, equity=Decimal("0"))
    denied = evaluate(**new_risk.replace(account=insolvent).as_kwargs())
    assert denied.rule("NON_POSITIVE_EQUITY").outcome is RuleOutcome.DENY
    assert denied.projected_leverage is None

    reducer = strict_reducer_inputs()
    insolvent_reducer = sealed_account(reducer, equity=Decimal("0"))
    allowed = evaluate(**reducer.replace(account=insolvent_reducer).as_kwargs())
    assert allowed.rule("NON_POSITIVE_EQUITY").outcome is RuleOutcome.PASS
    assert allowed.projected_leverage is None
    assert allowed.decision is Decision.ALLOW


def test_reducer_exempts_reduce_only_mode_and_trading_window() -> None:
    inputs = strict_reducer_inputs()
    account = sealed_account(inputs, halt_state=HaltState.REDUCE_ONLY)
    policy = sealed_policy(
        inputs,
        allowed_weekly_windows=(WeeklyWindow(start_minute_utc=0, end_minute_utc=1),),
    )

    result = evaluate(**inputs.replace(policy=policy, account=account).as_kwargs())

    assert result.rule("REDUCE_ONLY_MODE").outcome is RuleOutcome.PASS
    assert result.rule("OUTSIDE_TRADING_WINDOW").outcome is RuleOutcome.PASS
    assert result.decision is Decision.ALLOW
