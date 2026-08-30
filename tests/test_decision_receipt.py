from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from mnemox_control.canonical import content_sha256
from mnemox_control.contracts import DecisionReceipt

VALID_HASH = "a" * 64


def valid_receipt_data() -> dict[str, object]:
    return {
        "receipt_id": UUID("33333333-3333-3333-3333-333333333333"),
        "intent_id": UUID("22222222-2222-2222-2222-222222222222"),
        "policy_id": UUID("11111111-1111-1111-1111-111111111111"),
        "policy_hash": VALID_HASH,
        "decision": "ALLOW",
        "reason_codes": (),
        "evaluated_at": datetime(2026, 8, 30, 8, 0, 2, tzinfo=timezone.utc),
        "order_intent_hash": "b" * 64,
        "broker_order_id": "broker-order-123",
        "previous_receipt_hash": None,
        "content_hash": None,
    }


def test_receipt_normalizes_reasons_and_hashes_without_mutation() -> None:
    data = valid_receipt_data()
    data.update(
        decision="DENY",
        reason_codes=(" leverage_limit ", "LEVERAGE_LIMIT", "daily_loss"),
        broker_order_id=None,
    )
    receipt = DecisionReceipt(**data)

    hashed = receipt.with_content_hash()

    assert receipt.reason_codes == ("DAILY_LOSS", "LEVERAGE_LIMIT")
    assert receipt.content_hash is None
    assert hashed.content_hash == content_sha256(receipt, exclude={"content_hash"})


@pytest.mark.parametrize("decision", ["DENY", "ESCALATE"])
def test_non_allow_receipt_disallows_broker_order_id(decision: str) -> None:
    data = valid_receipt_data()
    data.update(decision=decision, reason_codes=("LIMIT",))

    with pytest.raises(ValidationError, match="broker_order_id"):
        DecisionReceipt(**data)


@pytest.mark.parametrize("decision", ["DENY", "ESCALATE"])
def test_non_allow_receipt_requires_reason_code(decision: str) -> None:
    data = valid_receipt_data()
    data.update(decision=decision, reason_codes=(), broker_order_id=None)

    with pytest.raises(ValidationError, match="reason_codes"):
        DecisionReceipt(**data)


def test_allow_receipt_may_omit_broker_order_id_before_submission() -> None:
    data = valid_receipt_data()
    data["broker_order_id"] = None

    assert DecisionReceipt(**data).broker_order_id is None


@pytest.mark.parametrize(
    "field",
    ["policy_hash", "order_intent_hash", "previous_receipt_hash", "content_hash"],
)
@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_receipt_rejects_invalid_hashes(field: str, value: str) -> None:
    data = valid_receipt_data()
    data[field] = value

    with pytest.raises(ValidationError, match=field):
        DecisionReceipt(**data)


def test_receipt_rejects_unknown_fields_and_mutation() -> None:
    data = valid_receipt_data()
    data["surprise"] = True
    with pytest.raises(ValidationError):
        DecisionReceipt(**data)

    receipt = DecisionReceipt(**valid_receipt_data())
    with pytest.raises(ValidationError):
        receipt.decision = "DENY"  # type: ignore[misc]
