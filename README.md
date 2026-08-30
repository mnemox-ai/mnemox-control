# Mnemox Control

Deterministic risk-control contracts and decision evidence for agentic trading.

Mnemox Control is the protocol boundary between a trading agent and order execution. An agent
proposes an `OrderIntent`; an independently owned policy constrains that proposal; the control
layer records the outcome as a verifiable `DecisionReceipt`.

This repository is the first, deliberately narrow protocol slice. It does **not** execute trades.

## Why this exists

Trading agents can generate and submit actions faster than a human can supervise them. Exchange
bots usually provide execution controls, but execution is not the same as independent risk
governance. Mnemox aims to make policy enforcement and decision evidence portable across agents,
strategies, and brokers.

The v0.1 package freezes three wire contracts:

- `PolicyBundle` — owner-defined account limits for a fixed validity window.
- `OrderIntent` — an agent's proposed order before execution.
- `DecisionReceipt` — an allow, deny, or escalate decision linked to its inputs.

All models reject unknown fields and are immutable. UUIDs and timestamps come from callers, while
financial values use `Decimal`. Canonical JSON and SHA-256 helpers make semantically identical
objects produce identical bytes and content identifiers.

## Install for development

Mnemox Control requires Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Example

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from mnemox_control import PolicyBundle

policy = PolicyBundle(
    policy_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d2f"),
    owner_id="owner-1",
    account_id="paper-account-1",
    broker="paper",
    allowed_symbols=("BTCUSDT", "ETHUSDT"),
    max_order_notional=Decimal("1000"),
    max_position_notional=Decimal("5000"),
    max_leverage=Decimal("2"),
    max_daily_loss=Decimal("250"),
    max_drawdown=Decimal("500"),
    approval_notional=Decimal("750"),
    valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
    expires_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    created_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
).with_content_hash()

assert policy.content_hash is not None
```

## Security boundary

SHA-256 content identifiers detect changes; they do not authenticate an owner. v0.1 does not
include digital signatures, key ownership, policy evaluation, persistence, networking, broker
credentials, broker adapters, or live-order submission. A future execution gateway must verify
signatures and policy authority before trusting a `PolicyBundle`.

Do not place API keys, exchange secrets, or live trading access in this package.

## Verify

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy src
.venv\Scripts\python -m build
```

## License

Apache-2.0.
