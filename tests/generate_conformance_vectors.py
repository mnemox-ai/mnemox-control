"""Print reviewed protocol v0.3 conformance vectors for repository updates."""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from decimal import Decimal

from factories import EvaluationInputs, valid_inputs

from mnemox_control.canonical import canonical_json_bytes
from mnemox_control.evaluator import evaluate


def multi_deny_inputs() -> EvaluationInputs:
    inputs = valid_inputs()
    policy = inputs.policy.model_copy(
        update={
            "allowed_symbols": ("ETHUSDT",),
            "max_open_orders": 0,
            "max_order_notional": Decimal("50"),
            "max_position_notional": Decimal("50"),
            "max_leverage": Decimal("1"),
            "max_daily_loss": Decimal("100"),
            "max_drawdown": Decimal("500"),
            "approval_notional": Decimal("25"),
            "content_hash": None,
        }
    ).with_content_hash()
    account = inputs.account.model_copy(
        update={
            "equity": Decimal("50"),
            "realized_pnl_today": Decimal("-100"),
            "drawdown_from_peak": Decimal("500"),
            "content_hash": None,
        }
    ).with_content_hash()
    market = inputs.market.model_copy(
        update={
            "observed_at": inputs.evaluated_at - timedelta(seconds=31),
            "content_hash": None,
        }
    ).with_content_hash()
    return inputs.replace(policy=policy, account=account, market=market)


def build_fixture(inputs: EvaluationInputs) -> dict[str, object]:
    result = evaluate(**inputs.as_kwargs())
    return {
        "inputs": {
            "policy": inputs.policy.model_dump(mode="json"),
            "intent": inputs.intent.model_dump(mode="json"),
            "account": inputs.account.model_dump(mode="json"),
            "market": inputs.market.model_dump(mode="json"),
            "instruments": inputs.instruments.model_dump(mode="json"),
            "evaluated_at": inputs.evaluated_at.isoformat().replace("+00:00", "Z"),
        },
        "expected": {
            "result": result.model_dump(mode="json"),
            "canonical_json": canonical_json_bytes(result).decode("utf-8"),
            "content_hash": result.content_hash,
        },
    }


def main() -> None:
    name = sys.argv[1]
    inputs = valid_inputs() if name == "basic-allow" else multi_deny_inputs()
    print(json.dumps(build_fixture(inputs), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
