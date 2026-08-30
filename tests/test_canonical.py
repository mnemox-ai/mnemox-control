from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel

from mnemox_control.canonical import canonical_json_bytes, content_sha256


class Fixture(BaseModel):
    amount: Decimal
    occurred_at: datetime


def test_canonical_json_normalizes_decimal_and_utc_timestamp() -> None:
    fixture = Fixture(
        amount=Decimal("10.5000"),
        occurred_at=datetime(2026, 8, 30, 16, tzinfo=timezone(timedelta(hours=8))),
    )

    assert canonical_json_bytes(fixture) == (
        b'{"amount":"10.5","occurred_at":"2026-08-30T08:00:00Z"}'
    )


def test_canonical_json_is_independent_of_model_field_order() -> None:
    class Forward(BaseModel):
        alpha: int
        beta: str

    class Reverse(BaseModel):
        beta: str
        alpha: int

    assert canonical_json_bytes(Forward(alpha=1, beta="two")) == canonical_json_bytes(
        Reverse(beta="two", alpha=1)
    )


def test_content_sha256_is_known_lowercase_digest() -> None:
    fixture = Fixture(
        amount=Decimal("10.5"),
        occurred_at=datetime(2026, 8, 30, 8, tzinfo=timezone.utc),
    )

    assert content_sha256(fixture) == "3f8cb9ccff1cadd57ee0838c0ba030ba527648b678bc56aab793248fbe4cbba0"


def test_canonical_json_rejects_naive_datetime() -> None:
    fixture = Fixture(amount=Decimal("1"), occurred_at=datetime(2026, 8, 30, 8))

    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_json_bytes(fixture)
