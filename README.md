# Mnemox Control

Mnemox Control is a broker-neutral Policy Evaluation Engine for agentic trading. It evaluates an
untrusted order intent against an owner policy and sealed account, market, and instrument state,
then returns deterministic proof-carrying evidence with 36 ordered rules.

This repository implements the v0.2 Policy Decision Point (PDP). It does **not** execute trades,
hold broker credentials, authenticate policy owners, reserve exposure, or issue single-use order
authorizations.

## Evaluate a conformance input

```python
import json
from datetime import datetime
from pathlib import Path

from mnemox_control import (
    InstrumentCatalog,
    MarketSnapshot,
    OrderIntent,
    PolicyBundle,
    TrustedAccountSnapshot,
    evaluate,
)

fixture = json.loads(Path("tests/conformance/v0.2/basic-allow.json").read_text(encoding="utf-8"))
inputs = fixture["inputs"]
result = evaluate(
    policy=PolicyBundle.model_validate(inputs["policy"]),
    intent=OrderIntent.model_validate(inputs["intent"]),
    account=TrustedAccountSnapshot.model_validate(inputs["account"]),
    market=MarketSnapshot.model_validate(inputs["market"]),
    instruments=InstrumentCatalog.model_validate(inputs["instruments"]),
    evaluated_at=datetime.fromisoformat(inputs["evaluated_at"].replace("Z", "+00:00")),
)

print(result.decision, result.content_hash)
```

An `ALLOW` result must **not** be sent directly to a broker. It is a static PDP result, not an
execution authorization. A production Policy Enforcement Point must verify authority and
revocation, atomically reserve capacity, issue and consume a single-use grant, submit idempotently,
and reconcile broker truth.

## What v0.2 guarantees

- Pure deterministic evaluation: no clock, storage, network, UUID, or randomness reads.
- Complete binding to policy, intent, account, market, instrument catalog, state version, and time.
- Full account-wide worst-case exposure; opposing pending orders never net.
- Exact `Decimal` quantities, prices, increments, notionals, and leverage.
- Known unsupported instruments deny instead of using an incorrect valuation formula.
- Strict monotonic reduce-only semantics with a data-driven exemption matrix.
- One structured result for every rule; dependent `SKIP` requires a prior `DENY`.
- `DENY` outranks `ESCALATE`, while all triggered evidence remains visible.
- Byte-identical Apache-licensed conformance vectors for independent implementations.

The full equations, rule order, temporal semantics, and conformance procedure are in
[`docs/protocol/evaluation-v0.2.md`](docs/protocol/evaluation-v0.2.md).

## Development

Mnemox Control requires Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy src
.venv\Scripts\python -m build
```

Hypothesis properties cover exposure monotonicity, pending-risk monotonicity, strict reductions,
determinism, hash binding, decision precedence, and input immutability. Conformance tests compare
the full result, canonical JSON, and SHA-256 byte for byte.

## Security boundary

Content hashes detect mutation but do not prove issuer identity or current authority. v0.2 has no
signature verification, policy registry, revocation lookup, atomic reservation, authorization
grant, broker adapter, execution receipt, reconciliation service, or coverage proof. These are
explicit future PEP/evidence layers, not implied capabilities of this kernel.

Do not place API keys, exchange secrets, broker sessions, or live-order access in this package.

`DecisionReceipt` remains importable for v0.1 compatibility but is deprecated. New integrations
use `EvaluationResult`.

## Licensing

- Python engine: `AGPL-3.0-only`, with separate commercial licensing available.
- Protocol specifications and conformance vectors: Apache License 2.0.
- Mnemox names and trademarks are excluded except for origin identification.

See [`LICENSE`](LICENSE), [`COMMERCIAL-LICENSE.md`](COMMERCIAL-LICENSE.md), and
[`docs/protocol/LICENSE`](docs/protocol/LICENSE).
