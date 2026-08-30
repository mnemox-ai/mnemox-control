# Mnemox Evaluation Kernel v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, broker-neutral Policy Decision Point that evaluates one order
intent against sealed policy, complete account state, market state, and instrument definitions,
without implying live-order authorization.

**Architecture:** Keep immutable wire contracts separate from pure calculations and rule
orchestration. `evaluate()` receives every source of time and state explicitly, emits one ordered
result per protocol rule, and never touches storage, network, credentials, randomness, or the
system clock. A compatibility facade preserves the public import surface while v0.1
`DecisionReceipt` is deprecated in favor of `EvaluationResult`.

**Tech Stack:** Python 3.12, Pydantic v2, `Decimal`, pytest, Hypothesis, Ruff, strict mypy,
Hatchling.

**Spec:** `docs/superpowers/specs/2026-08-30-evaluation-kernel-v0.2-design.md`

## Global Constraints

- Python 3.12 or newer.
- No production behavior without an observed failing test first.
- All wire models are frozen and reject unknown fields.
- All financial arithmetic uses `Decimal`; never introduce binary float arithmetic.
- Evaluation is deterministic and side-effect free.
- `ALLOW` is an evaluation outcome, never a broker authorization.
- v0.2 supports only SPOT and LINEAR_PERPETUAL with ONE_WAY positions.
- Opposite pending orders never offset each other in the worst-case exposure envelope.
- Missing valuation coverage denies evaluation; unvalued exposure is never dropped.
- Protocol documents and language-neutral vectors are Apache-2.0; the Python engine is
  AGPL-3.0 with a separate commercial license from Mnemox.
- Every task ends with its focused tests plus the full existing suite.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/mnemox_control/contracts.py` | Existing policy/intent contracts, upgraded PolicyBundle v0.2, compatibility exports |
| `src/mnemox_control/state.py` | Instrument, market, position, open-order, and trusted-account contracts |
| `src/mnemox_control/evaluation.py` | Reason taxonomy, rule evidence, position effects, and EvaluationResult contract |
| `src/mnemox_control/calculations.py` | Pure signed-position, price, increment, and worst-case exposure calculations |
| `src/mnemox_control/evaluator.py` | Fixed-order rule orchestration and final decision precedence |
| `src/mnemox_control/__init__.py` | Stable public API exports |
| `tests/factories.py` | Deterministic valid v0.2 fixtures shared by evaluator tests |
| `tests/test_distribution_policy.py` | License/package boundary tests |
| `tests/test_state_contracts.py` | Instrument, market, account, and pending-order contract tests |
| `tests/test_policy_v02.py` | Policy revision, windows, limits, and migration tests |
| `tests/test_evaluation_contracts.py` | Reason/rule/result contract tests |
| `tests/test_calculations.py` | Signed position and conservative exposure unit tests |
| `tests/test_evaluator_preflight.py` | Integrity, binding, coverage, freshness, and temporal rules |
| `tests/test_evaluator_risk.py` | Halts, limits, reduction exemptions, reversal, and precedence rules |
| `tests/test_evaluator_properties.py` | Generated invariant tests |
| `tests/conformance/v0.2/basic-allow.json` | Language-neutral canonical ALLOW vector |
| `tests/conformance/v0.2/multi-deny.json` | Language-neutral multi-rule DENY vector |
| `docs/protocol/LICENSE` | Apache-2.0 protocol-material license notice |
| `LICENSE` and `LICENSES/*` | Root license map and complete license texts |

---

### Task 1: Establish the Distribution and Test Boundary

**Files:**
- Modify: `pyproject.toml`
- Create: `LICENSE`
- Create: `LICENSES/AGPL-3.0.txt`
- Create: `LICENSES/Apache-2.0.txt`
- Create: `COMMERCIAL-LICENSE.md`
- Create: `docs/protocol/LICENSE`
- Create: `tests/test_distribution_policy.py`

**Interfaces:**
- Consumes: approved distribution boundary in the v0.2 spec.
- Produces: installable engine metadata under `AGPL-3.0-only`; Apache protocol-material notice;
  Hypothesis in the dev environment.

- [ ] **Step 1: Write the failing distribution-policy test**

```python
from pathlib import Path
import tomllib

ROOT = Path(__file__).parents[1]


def test_engine_and_protocol_have_distinct_license_boundaries() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "AGPL-3.0-only"
    assert project["version"] == "0.2.0"
    assert (ROOT / "LICENSES" / "AGPL-3.0.txt").is_file()
    assert (ROOT / "LICENSES" / "Apache-2.0.txt").is_file()
    assert "Apache License" in (ROOT / "docs" / "protocol" / "LICENSE").read_text("utf-8")


def test_property_test_dependency_is_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(item.startswith("hypothesis>=") for item in project["optional-dependencies"]["dev"])
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `.venv\Scripts\python -m pytest tests/test_distribution_policy.py -q`

Expected: FAIL because the package still declares Apache-2.0 and the license files do not exist.

- [ ] **Step 3: Add exact license metadata and notices**

Change `[project].license` to the SPDX expression `AGPL-3.0-only`, bump the package to `0.2.0`, add `hypothesis>=6.138` to the
dev extra; add the unmodified official AGPL-3.0 and Apache-2.0 texts; add a root map stating that
Python engine source is AGPL-3.0-only unless separately commercially licensed and protocol
materials under `docs/protocol` plus conformance JSON are Apache-2.0. `COMMERCIAL-LICENSE.md`
must say commercial terms require a written agreement from Mnemox and grants no rights by itself.

```toml
[project]
version = "0.2.0"
license = "AGPL-3.0-only"

[project.optional-dependencies]
dev = ["build>=1.3", "hypothesis>=6.138", "mypy>=1.18", "pytest>=9.0", "ruff>=0.13"]
```

- [ ] **Step 4: Reinstall and verify GREEN**

Run: `.venv\Scripts\python -m pip install -e ".[dev]"`

Run: `.venv\Scripts\python -m pytest tests/test_distribution_policy.py -q`

Expected: 2 passed.

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv\Scripts\python -m pytest -q`

Commit: `build: establish engine license boundary`

---

### Task 2: Define Instrument and Market Coverage Contracts

**Files:**
- Create: `src/mnemox_control/state.py`
- Create: `tests/test_state_contracts.py`
- Modify: `src/mnemox_control/__init__.py`

**Interfaces:**
- Consumes: `StrictFrozenModel`, `NonBlankStr`, numeric aliases, and content hashing from existing
  contracts/canonical modules.
- Produces: `InstrumentType`, `PositionMode`, `InstrumentSpec`, `InstrumentCatalog`, `MarketQuote`,
  and `MarketSnapshot`.

- [ ] **Step 1: Write RED tests for strict supported instruments and sealed catalogs**

```python
@pytest.fixture
def valid_instrument_data() -> dict[str, object]:
    return {
        "instrument_id": "binance:BTCUSDT",
        "version": "2026-08-30",
        "broker": "binance-demo",
        "symbol": "BTCUSDT",
        "instrument_type": "LINEAR_PERPETUAL",
        "position_mode": "ONE_WAY",
        "allows_short": True,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "contract_multiplier": Decimal("1"),
        "quantity_step": Decimal("0.001"),
        "price_tick": Decimal("0.1"),
        "min_quantity": Decimal("0.001"),
        "min_notional": Decimal("5"),
    }


@pytest.fixture
def valid_instrument(valid_instrument_data: dict[str, object]) -> InstrumentSpec:
    return InstrumentSpec(**valid_instrument_data)


@pytest.fixture
def valid_catalog(valid_instrument: InstrumentSpec) -> InstrumentCatalog:
    return InstrumentCatalog(
        catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
        version="2026-08-30",
        broker="binance-demo",
        instruments=(valid_instrument,),
        observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
    )


def test_catalog_rejects_duplicate_symbols(valid_instrument: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="unique"):
        InstrumentCatalog(
            catalog_id=UUID("018f84d7-46a7-7e8d-97de-4a3f13635d40"),
            version="2026-08-30",
            broker="binance-demo",
            instruments=(valid_instrument, valid_instrument),
            observed_at=datetime(2026, 8, 30, 8, tzinfo=UTC),
        )


def test_instrument_represents_known_but_unsupported_type(
    valid_instrument_data: dict[str, object],
) -> None:
    valid_instrument_data["instrument_type"] = "INVERSE_PERPETUAL"
    assert InstrumentSpec(**valid_instrument_data).instrument_type == "INVERSE_PERPETUAL"


def test_catalog_hashes_without_mutation(valid_catalog: InstrumentCatalog) -> None:
    sealed = valid_catalog.with_content_hash()
    assert valid_catalog.content_hash is None
    assert sealed.content_hash == content_sha256(valid_catalog, exclude={"content_hash"})
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python -m pytest tests/test_state_contracts.py -q`

Expected: collection fails because `mnemox_control.state` does not exist.

- [ ] **Step 3: Implement minimal instrument/catalog models**

Use the complete recognized `StrEnum` vocabulary from the spec; evaluator support is narrower than
wire representation. Validate positive multiplier, steps, minimums, unique
instrument IDs/symbols, broker binding, uppercase symbols/assets, and lowercase SHA-256 format.
Catalog `with_content_hash()` excludes only `content_hash`.

```python
class InstrumentType(StrEnum):
    SPOT = "SPOT"
    LINEAR_PERPETUAL = "LINEAR_PERPETUAL"
    INVERSE_PERPETUAL = "INVERSE_PERPETUAL"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class PositionMode(StrEnum):
    ONE_WAY = "ONE_WAY"
    HEDGE = "HEDGE"


class InstrumentCatalog(StrictFrozenModel):
    catalog_id: UUID
    version: NonBlankStr
    broker: NonBlankStr
    instruments: tuple[InstrumentSpec, ...]
    observed_at: datetime
    content_hash: str | None = None
```

- [ ] **Step 4: Add RED tests for complete market quotes**

```python
def test_market_snapshot_rejects_duplicate_quote_symbols(valid_quote: MarketQuote) -> None:
    with pytest.raises(ValidationError, match="unique"):
        MarketSnapshot(**market_data(quotes=(valid_quote, valid_quote)))


@pytest.mark.parametrize("bid,ask", [("0", "100"), ("101", "100")])
def test_market_quote_requires_positive_ordered_book(bid: str, ask: str) -> None:
    with pytest.raises(ValidationError):
        MarketQuote(symbol="BTCUSDT", bid=bid, ask=ask, mark="100")
```

- [ ] **Step 5: Implement market models and run GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_state_contracts.py -q`

Run: `.venv\Scripts\python -m pytest -q`

- [ ] **Step 6: Commit**

Commit: `feat: define sealed instrument and market state`

---

### Task 3: Define Trusted Account and Pending Exposure Contracts

**Files:**
- Modify: `src/mnemox_control/state.py`
- Modify: `tests/test_state_contracts.py`
- Modify: `src/mnemox_control/__init__.py`

**Interfaces:**
- Consumes: public `Side` enum and strict frozen base.
- Produces: `Position`, `OpenOrderStatus`, `OpenOrderExposure`, `HaltState`, and
  `TrustedAccountSnapshot`.

- [ ] **Step 1: Write RED tests for signed positions and non-terminal orders**

```python
@pytest.fixture
def valid_account_data() -> dict[str, object]:
    return {
        "snapshot_id": UUID("018f84d7-46a7-7e8d-97de-4a3f13635d41"),
        "state_version": 7,
        "source": "binance-user-stream",
        "account_id": "paper-1",
        "broker": "binance-demo",
        "equity": Decimal("10000"),
        "cash_balance": Decimal("10000"),
        "realized_pnl_today": Decimal("0"),
        "realized_pnl_period_start": datetime(2026, 8, 30, tzinfo=UTC),
        "realized_pnl_period_end": datetime(2026, 8, 31, tzinfo=UTC),
        "drawdown_from_peak": Decimal("0"),
        "positions": (),
        "open_orders": (),
        "halt_state": "NORMAL",
        "observed_at": datetime(2026, 8, 30, 8, tzinfo=UTC),
    }


def test_account_rejects_duplicate_positions(valid_account_data: dict[str, object]) -> None:
    position = Position(symbol="BTCUSDT", signed_quantity="1")
    valid_account_data["positions"] = (position, position)
    with pytest.raises(ValidationError, match="position symbols"):
        TrustedAccountSnapshot(**valid_account_data)


def test_unknown_order_requires_full_positive_remaining_exposure() -> None:
    order = OpenOrderExposure(
        broker_order_id="order-1",
        intent_id=None,
        symbol="BTCUSDT",
        side="BUY",
        remaining_quantity="0.2",
        reduce_only=False,
        reference_price="100000",
        status="UNKNOWN",
    )
    assert order.remaining_quantity == Decimal("0.2")
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python -m pytest tests/test_state_contracts.py -q`

Expected: import failures for the new account-state types.

- [ ] **Step 3: Implement minimal account-state models**

Normalize/sort positions and orders by stable keys. Require unique position symbols and broker
order IDs, positive state version, timezone-aware half-open P&L window, non-negative drawdown,
positive remaining quantities/reference prices, and canonical content hashing.

```python
class TrustedAccountSnapshot(StrictFrozenModel):
    snapshot_id: UUID
    state_version: Annotated[int, Field(gt=0)]
    source: NonBlankStr
    account_id: NonBlankStr
    broker: NonBlankStr
    equity: Decimal
    cash_balance: Decimal
    realized_pnl_today: Decimal
    realized_pnl_period_start: datetime
    realized_pnl_period_end: datetime
    drawdown_from_peak: NonNegativeDecimal
    positions: tuple[Position, ...]
    open_orders: tuple[OpenOrderExposure, ...]
    halt_state: HaltState
    observed_at: datetime
    content_hash: str | None = None
```

- [ ] **Step 4: Add boundary/frozen/hash RED tests, implement, and run GREEN**

Cover future-invalid P&L window shape, unknown fields, duplicate IDs, UTC normalization, model
immutability, and hash mismatch formatting at the contract layer.

Run: `.venv\Scripts\python -m pytest tests/test_state_contracts.py -q`

Run: `.venv\Scripts\python -m pytest -q`

- [ ] **Step 5: Commit**

Commit: `feat: define trusted account risk snapshot`

---

### Task 4: Upgrade PolicyBundle to Protocol v0.2

**Files:**
- Modify: `src/mnemox_control/contracts.py`
- Create: `tests/test_policy_v02.py`
- Modify: `tests/test_policy_bundle.py`
- Create: `tests/factories.py`

**Interfaces:**
- Consumes: existing PolicyBundle v0.1 normalization and hashing.
- Produces: `WeeklyWindow` and PolicyBundle v0.2 with revision linkage, freshness, price, order,
  reversal, risk-day, and weekly-window controls.
- Produces shared test helpers with exact public names:
  - `valid_inputs() -> EvaluationInputs`
  - `inputs_for_quantity(quantity: Decimal) -> EvaluationInputs`
  - `buy(symbol: str, quantity: str) -> OpenOrderExposure`
  - `sell(symbol: str, quantity: str) -> OpenOrderExposure`
  - `buy_intent(symbol: str, quantity: str) -> OrderIntent`
  - `catalog_btc(multiplier: str = "1") -> InstrumentCatalog`
  - `market_btc(mark: str = "100") -> MarketSnapshot`
  - `policy_data() -> dict[str, object]`

```python
@dataclass(frozen=True)
class EvaluationInputs:
    policy: PolicyBundle
    intent: OrderIntent
    account: TrustedAccountSnapshot
    market: MarketSnapshot
    instruments: InstrumentCatalog
    evaluated_at: datetime

    def as_kwargs(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "intent": self.intent,
            "account": self.account,
            "market": self.market,
            "instruments": self.instruments,
            "evaluated_at": self.evaluated_at,
        }

    def replace(self, **changes: object) -> Self:
        return dataclasses.replace(self, **changes)
```

- [ ] **Step 1: Create deterministic shared factories and write the RED version test**

```python
def test_policy_v02_requires_revision_link_shape() -> None:
    valid_policy_data = policy_data()
    policy = PolicyBundle(**valid_policy_data)
    assert policy.version == "0.2"
    assert policy.revision == 1
    assert policy.previous_policy_hash is None


def test_later_revision_requires_previous_hash() -> None:
    valid_policy_data = policy_data()
    valid_policy_data.update(revision=2, previous_policy_hash=None)
    with pytest.raises(ValidationError, match="previous_policy_hash"):
        PolicyBundle(**valid_policy_data)
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python -m pytest tests/test_policy_v02.py -q`

Expected: FAIL because version is still 0.1 and v0.2 fields are absent.

- [ ] **Step 3: Implement WeeklyWindow and v0.2 fields**

Require revision >= 1; revision 1 has no predecessor; later revisions require a valid hash.
Require positive monetary/exposure limits and positive freshness ages, non-negative price
deviation/open-order count/approval threshold, valid UTC risk hour, and sorted non-overlapping
weekly windows covering explicit policy time only.

```python
class WeeklyWindow(StrictFrozenModel):
    start_minute_utc: Annotated[int, Field(ge=0, lt=10080)]
    end_minute_utc: Annotated[int, Field(gt=0, le=10080)]


class PolicyBundle(StrictFrozenModel):
    version: Literal["0.2"] = "0.2"
    revision: Annotated[int, Field(ge=1)]
    previous_policy_hash: str | None = None
    max_state_age_seconds: Annotated[int, Field(gt=0)]
    max_market_age_seconds: Annotated[int, Field(gt=0)]
    max_instrument_age_seconds: Annotated[int, Field(gt=0)]
    max_price_deviation_bps: NonNegativeDecimal
    max_open_orders: Annotated[int, Field(ge=0)]
    max_order_quantity: PositiveDecimal | None
    allow_position_reversal: bool
    risk_day_start_hour_utc: Annotated[int, Field(ge=0, le=23)]
    allowed_weekly_windows: tuple[WeeklyWindow, ...]
```

- [ ] **Step 4: Add RED boundary tests**

Test overlapping/empty windows, `[0, 10080)` 24/7, zero monetary limits, approval above order
limit, missing predecessor, predecessor on revision 1, invalid freshness, and hash stability.

- [ ] **Step 5: Update v0.1 fixtures as an explicit breaking migration and run GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_policy_v02.py tests/test_policy_bundle.py -q`

Run: `.venv\Scripts\python -m pytest -q`

- [ ] **Step 6: Commit**

Commit: `feat: upgrade policy bundle to protocol v0.2`

---

### Task 5: Define Evaluation Evidence Contracts

**Files:**
- Create: `src/mnemox_control/evaluation.py`
- Create: `tests/test_evaluation_contracts.py`
- Modify: `src/mnemox_control/__init__.py`

**Interfaces:**
- Consumes: `Decision`, canonical hashing, strict frozen base.
- Produces: `RuleOutcome`, `PositionEffect`, the 36-member `ReasonCode`, `RuleResult`, and
  `EvaluationResult`.

- [ ] **Step 1: Write RED tests for ordered structured evidence**

```python
def test_skip_requires_a_deny_dependency() -> None:
    with pytest.raises(ValidationError, match="blocked_by"):
        RuleResult(code="LEVERAGE_EXCEEDED", outcome="SKIP", blocked_by=())


def test_rule_subjects_are_normalized() -> None:
    result = RuleResult(
        code="HASH_MISMATCH",
        outcome="DENY",
        subjects=("market", "account", "market"),
    )
    assert result.subjects == ("account", "market")
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python -m pytest tests/test_evaluation_contracts.py -q`

Expected: collection fails because evaluation contracts do not exist.

- [ ] **Step 3: Implement exact enums and frozen result models**

Copy the protocol reason order exactly from the approved spec. `EvaluationResult` requires exactly
one `RuleResult` per reason in protocol order, rejects duplicate/missing codes, validates lowercase
hashes, and hashes without mutation.

```python
class RuleOutcome(StrEnum):
    PASS = "PASS"
    ESCALATE = "ESCALATE"
    DENY = "DENY"
    SKIP = "SKIP"


class EvaluationResult(StrictFrozenModel):
    protocol_version: Literal["0.2"] = "0.2"
    decision: Decision
    rules: tuple[RuleResult, ...]
    content_hash: str | None = None

    def rule(self, code: ReasonCode | str) -> RuleResult:
        wanted = ReasonCode(code)
        return next(item for item in self.rules if item.code is wanted)
```

- [ ] **Step 4: Add RED tests for false PASS prevention and deterministic hashing**

Prove SKIP names prior DENY codes, SKIP cannot exist in an otherwise ALLOW result, nullable metrics
are allowed only with blocking DENY evidence, and reordered construction yields the same content
hash.

- [ ] **Step 5: Implement validations and run GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_evaluation_contracts.py -q`

Run: `.venv\Scripts\python -m pytest -q`

- [ ] **Step 6: Commit**

Commit: `feat: define evaluation evidence contract`

---

### Task 6: Implement Signed-Position and Worst-Case Exposure Calculations

**Files:**
- Create: `src/mnemox_control/calculations.py`
- Create: `tests/test_calculations.py`

**Interfaces:**
- Consumes: `OrderIntent`, state contracts, `PositionEffect`.
- Produces:
  - `signed_order_quantity(intent: OrderIntent) -> Decimal`
  - `classify_position_effect(current: Decimal, proposed: Decimal) -> PositionEffect`
  - `reference_price(intent: OrderIntent, quote: MarketQuote) -> Decimal`
  - `is_step_aligned(value: Decimal, step: Decimal) -> bool`
  - `build_exposure_metrics(*, current: Mapping[str, Decimal], pending: tuple[OpenOrderExposure, ...], proposed: OrderIntent, catalog: InstrumentCatalog, market: MarketSnapshot, equity: Decimal) -> ExposureMetrics`

- [ ] **Step 1: Write RED tests for all signed transition classes**

```python
@pytest.mark.parametrize(
    ("current", "delta", "expected"),
    [("0", "1", "OPEN"), ("1", "1", "INCREASE"), ("2", "-1", "REDUCE"),
     ("1", "-1", "CLOSE"), ("1", "-2", "REVERSE")],
)
def test_classifies_position_effect(current: str, delta: str, expected: str) -> None:
    proposed = Decimal(current) + Decimal(delta)
    assert classify_position_effect(Decimal(current), proposed).value == expected
```

- [ ] **Step 2: Run RED, implement signed helpers, and verify GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_calculations.py -q`

- [ ] **Step 3: Write RED tests proving opposite pending orders do not net**

```python
def test_opposite_pending_orders_use_larger_absolute_envelope() -> None:
    metrics = build_exposure_metrics(
        current={"BTCUSDT": Decimal("1")},
        pending=(buy("BTCUSDT", "2"), sell("BTCUSDT", "4")),
        proposed=buy_intent("BTCUSDT", "1"),
        catalog=catalog_btc(multiplier="1"),
        market=market_btc(mark="100"),
        equity=Decimal("1000"),
    )
    assert metrics.worst_case_quantities["BTCUSDT"] == Decimal("4")
    assert metrics.projected_gross_exposure == Decimal("400")
```

- [ ] **Step 4: Implement conservative envelope and valuation**

For each symbol, compute independent all-BUY and all-SELL envelopes, include UNKNOWN in full,
ignore reduce-only orders as capacity reducers, choose the larger absolute quantity, and value
with the catalog multiplier and `max(mark, reference_price)` where an executable order price
applies. Raise a typed calculation-coverage error listing every missing catalog/quote symbol.

```python
@dataclass(frozen=True)
class ExposureMetrics:
    current_position_quantity: Decimal
    proposed_fill_position_quantity: Decimal
    worst_case_position_quantities: Mapping[str, Decimal]
    worst_case_position_notional: Decimal
    projected_gross_exposure: Decimal
    projected_leverage: Decimal | None
    position_effect: PositionEffect
```

- [ ] **Step 5: Add price, increment, short, and reduce-only boundary tests**

Prove MARKET BUY uses ask, MARKET SELL uses bid, LIMIT/STOP use declared prices, Decimal modulo
enforces exact steps/ticks, and no float appears in returned metrics.

- [ ] **Step 6: Run focused/full GREEN and commit**

Run: `.venv\Scripts\python -m pytest tests/test_calculations.py -q`

Run: `.venv\Scripts\python -m pytest -q`

Commit: `feat: calculate conservative account exposure`

---

### Task 7: Implement Evaluator Integrity, Binding, and Temporal Preflight

**Files:**
- Create: `src/mnemox_control/evaluator.py`
- Create: `tests/test_evaluator_preflight.py`
- Modify: `src/mnemox_control/__init__.py`

**Interfaces:**
- Consumes: all v0.2 contracts and calculation helpers.
- Produces: `evaluate(*, policy: PolicyBundle, intent: OrderIntent, account:
  TrustedAccountSnapshot, market: MarketSnapshot, instruments: InstrumentCatalog, evaluated_at:
  datetime) -> EvaluationResult`.

- [ ] **Step 1: Write the first RED end-to-end ALLOW test**

Use sealed policy/account/market/catalog factories, a small BTCUSDT MARKET BUY, zero positions,
fresh timestamps, and wide limits. Assert all bound hashes, computed intent hash, state version,
reference price, decision ALLOW, exactly 36 ordered rules, and result content hash.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python -m pytest tests/test_evaluator_preflight.py -q`

Expected: import failure because `evaluate` does not exist.

- [ ] **Step 3: Implement a fixed rule-table skeleton and ALLOW path**

Create one result for every ReasonCode in enum order. Default PASS is allowed only after its
dependencies are evaluated. Compute all canonical hashes before semantic rules.

```python
def evaluate(
    *,
    policy: PolicyBundle,
    intent: OrderIntent,
    account: TrustedAccountSnapshot,
    market: MarketSnapshot,
    instruments: InstrumentCatalog,
    evaluated_at: datetime,
) -> EvaluationResult:
    context = _EvaluationContext.from_inputs(
        policy=policy,
        intent=intent,
        account=account,
        market=market,
        instruments=instruments,
        evaluated_at=evaluated_at,
    )
    rule_results = tuple(rule.evaluate(context) for rule in RULES)
    return _build_result(context, rule_results).with_content_hash()
```

- [ ] **Step 4: Add RED integrity and binding cases**

Parametrize missing/mismatched content hash across policy, account, market, and catalog. Parametrize
account/broker/symbol inconsistencies, missing market/catalog coverage, unsupported instrument,
and short-forbidden state. Assert aggregate sorted `subjects` and dependent SKIPs.

- [ ] **Step 5: Implement integrity, binding, coverage, and dependency SKIP rules**

No exception escapes for a semantically valid but denied evaluation. Structurally invalid models
continue to fail at Pydantic construction.

- [ ] **Step 6: Add RED time-window cases and implement exact boundaries**

Cover future/stale account, market, and catalog timestamps; exact-age pass; half-open policy
validity; P&L window reset at configured UTC hour; and weekly `[start, end)` behavior.

- [ ] **Step 7: Run focused/full GREEN and commit**

Run: `.venv\Scripts\python -m pytest tests/test_evaluator_preflight.py -q`

Run: `.venv\Scripts\python -m pytest -q`

Commit: `feat: evaluate sealed state and temporal bindings`

---

### Task 8: Implement Risk Rules, Exemptions, and Decision Precedence

**Files:**
- Modify: `src/mnemox_control/evaluator.py`
- Create: `tests/test_evaluator_risk.py`

**Interfaces:**
- Consumes: preflight rule table plus `ExposureMetrics`.
- Produces: all halt, price, reduce-only, reversal, order, position, leverage, loss, drawdown, and
  human-approval behavior from the normative exemption matrix.

- [ ] **Step 1: Write RED tests for hard-limit precedence**

```python
def test_deny_outranks_human_approval() -> None:
    inputs = valid_inputs()
    policy = inputs.policy.model_copy(
        update={"max_order_notional": Decimal("50"), "approval_notional": Decimal("25")}
    ).with_content_hash()
    intent = inputs.intent.model_copy(update={"quantity": Decimal("1")})
    inputs = inputs.replace(policy=policy, intent=intent)
    result = evaluate(**inputs.as_kwargs())
    assert result.decision is Decision.DENY
    assert result.rule("ORDER_NOTIONAL_EXCEEDED").outcome is RuleOutcome.DENY
    assert result.rule("HUMAN_APPROVAL_REQUIRED").outcome is RuleOutcome.ESCALATE
```

- [ ] **Step 2: Run RED and implement scalar hard limits plus precedence**

Implement inclusive limits exactly as specified; daily loss and drawdown trigger at their positive
amount thresholds; equality at maximum order/position/leverage/open-order limit passes.

- [ ] **Step 3: Write RED tests for long/short/reversal/reduce-only semantics**

Cover long/short increase, close, valid partial reduction, zero crossing, pending-order uncertainty,
disallowed short, and policy-controlled ordinary reversal.

- [ ] **Step 4: Implement position rules and the data-driven exemption matrix**

The exemption table maps each reason code to `ALWAYS`, `NEW_RISK_ONLY`, or `NORMAL_PATH_BLOCKER`.
Only a validated `reduce_only=True` monotonic reduction activates `NEW_RISK_ONLY` exemptions.
FULL_HALT and RECONCILE_REQUIRED remain DENY on the normal API.

```python
class EnforcementClass(StrEnum):
    ALWAYS = "ALWAYS"
    NEW_RISK_ONLY = "NEW_RISK_ONLY"
    NORMAL_PATH_BLOCKER = "NORMAL_PATH_BLOCKER"


_NORMAL_PATH_BLOCKERS = frozenset({
    ReasonCode.RECONCILE_REQUIRED,
    ReasonCode.FULL_HALT_ACTIVE,
})
_NEW_RISK_ONLY = frozenset({
    ReasonCode.OUTSIDE_TRADING_WINDOW,
    ReasonCode.SOFT_HALT_ACTIVE,
    ReasonCode.REDUCE_ONLY_MODE,
    ReasonCode.SYMBOL_NOT_ALLOWED,
    ReasonCode.SHORT_POSITION_FORBIDDEN,
    ReasonCode.OPEN_ORDER_LIMIT_EXCEEDED,
    ReasonCode.ORDER_QUANTITY_EXCEEDED,
    ReasonCode.ORDER_NOTIONAL_EXCEEDED,
    ReasonCode.POSITION_NOTIONAL_EXCEEDED,
    ReasonCode.LEVERAGE_EXCEEDED,
    ReasonCode.NON_POSITIVE_EQUITY,
    ReasonCode.DAILY_LOSS_LIMIT_REACHED,
    ReasonCode.DRAWDOWN_LIMIT_REACHED,
    ReasonCode.HUMAN_APPROVAL_REQUIRED,
})
_ALWAYS = frozenset(ReasonCode) - _NORMAL_PATH_BLOCKERS - _NEW_RISK_ONLY
assert _ALWAYS | _NORMAL_PATH_BLOCKERS | _NEW_RISK_ONLY == frozenset(ReasonCode)
```

- [ ] **Step 5: Write RED halt/loss/allowlist/trading-window exemption tests**

For each `NEW_RISK_ONLY` rule, run the same account condition with a risk increase (DENY) and a
strict reducer (PASS). Assert price/increment/hash/freshness failures still deny reducers.

- [ ] **Step 6: Implement remaining rules and ordered evidence**

Ensure all triggered rules remain visible after a denial and every non-triggered evaluable rule is
PASS. Human approval applies only to otherwise valid non-reduce-only orders at or above threshold.

- [ ] **Step 7: Run focused/full GREEN and commit**

Run: `.venv\Scripts\python -m pytest tests/test_evaluator_risk.py -q`

Run: `.venv\Scripts\python -m pytest -q`

Commit: `feat: enforce deterministic risk policy decisions`

---

### Task 9: Prove Invariants and Publish Conformance Vectors

**Files:**
- Create: `tests/test_evaluator_properties.py`
- Create: `tests/test_conformance.py`
- Create: `tests/conformance/v0.2/basic-allow.json`
- Create: `tests/conformance/v0.2/multi-deny.json`
- Create: `docs/protocol/evaluation-v0.2.md`
- Modify: `README.md`
- Modify: `src/mnemox_control/contracts.py`

**Interfaces:**
- Consumes: public evaluator API and canonical serializer.
- Produces: generated invariant evidence, byte-identical language-neutral fixtures, public protocol
  explanation, and a deprecated v0.1 DecisionReceipt compatibility export.

- [ ] **Step 1: Write RED Hypothesis invariants**

```python
@given(current=decimals(min_value="0", max_value="100"), extra=decimals(min_value="0.001"))
def test_more_risk_never_reduces_worst_case_exposure(current: Decimal, extra: Decimal) -> None:
    smaller = evaluate(**inputs_for_quantity(current).as_kwargs())
    larger = evaluate(**inputs_for_quantity(current + extra).as_kwargs())
    assert larger.projected_gross_exposure >= smaller.projected_gross_exposure
```

Also prove pending exposure monotonicity, reduce-only absolute reduction, any bound-input mutation
changes result hash, construction-order independence, DENY precedence, and input immutability.

- [ ] **Step 2: Run property RED/GREEN and preserve reproducibility**

Run: `.venv\Scripts\python -m pytest tests/test_evaluator_properties.py -q`

Use bounded strategies with exact decimals and fixed protocol datetimes; do not suppress failing
examples or weaken health checks to obtain GREEN.

- [ ] **Step 3: Write RED conformance loader tests**

Each JSON file contains `policy`, `intent`, `account`, `market`, `instruments`, `evaluated_at`, and
`expected` with decision, complete ordered rules, metrics, canonical JSON, and content hash. The
test reconstructs models, runs `evaluate`, and requires an exact expected match.

```python
fixture = json.loads(path.read_text(encoding="utf-8"))
result = evaluate(
    policy=PolicyBundle.model_validate(fixture["inputs"]["policy"]),
    intent=OrderIntent.model_validate(fixture["inputs"]["intent"]),
    account=TrustedAccountSnapshot.model_validate(fixture["inputs"]["account"]),
    market=MarketSnapshot.model_validate(fixture["inputs"]["market"]),
    instruments=InstrumentCatalog.model_validate(fixture["inputs"]["instruments"]),
    evaluated_at=datetime.fromisoformat(fixture["inputs"]["evaluated_at"].replace("Z", "+00:00")),
)
assert result.model_dump(mode="json") == fixture["expected"]["result"]
assert canonical_json_bytes(result).decode("utf-8") == fixture["expected"]["canonical_json"]
assert result.content_hash == fixture["expected"]["content_hash"]
```

- [ ] **Step 4: Add two reviewed vectors and verify byte identity**

`basic-allow.json` is a fresh small MARKET BUY. `multi-deny.json` combines stale market,
disallowed symbol, open-order overflow, order/position/leverage violations, loss, drawdown, and
approval evidence so precedence and SKIP rules are externally testable.

Run: `.venv\Scripts\python -m pytest tests/test_conformance.py -q`

- [ ] **Step 5: Document protocol and v0.1 migration**

README must show `evaluate()` and state in the first example that ALLOW cannot be sent directly to
a broker. Protocol docs must define canonical inputs, rule order, equations, exemption classes,
license, and conformance procedure. Keep `DecisionReceipt` importable but mark it deprecated and
remove it from the recommended flow; no runtime warning is emitted because wire parsing must stay
deterministic.

- [ ] **Step 6: Run full GREEN and commit**

Run: `.venv\Scripts\python -m pytest -q`

Commit: `docs: publish evaluation protocol v0.2 vectors`

---

### Task 10: Complete the Python 3.12 Release Gate

**Files:**
- Modify: `AGENTS.md`
- Modify: `tasks.txt`
- Modify: `docs/superpowers/plans/2026-08-30-evaluation-kernel-v0.2.md`

**Interfaces:**
- Consumes: the complete v0.2 tree.
- Produces: fresh verification evidence, distributable artifacts, recorded status, and a clean
  feature branch.

- [ ] **Step 1: Rebuild the Python 3.12 environment from declared metadata**

Run: `.venv\Scripts\python -m pip install -e ".[dev]"`

Run: `.venv\Scripts\python --version`

Expected: Python 3.12.x.

- [ ] **Step 2: Run every release gate fresh**

Run: `.venv\Scripts\python -m pytest -q`

Run: `.venv\Scripts\python -m ruff check .`

Run: `.venv\Scripts\python -m mypy src`

Run: `.venv\Scripts\python -m build`

Expected: all exit 0 with no warnings attributable to project code.

- [ ] **Step 3: Inspect wheel contents and metadata**

Run:

```powershell
.venv\Scripts\python -c "import glob,zipfile; p=glob.glob('dist/*.whl')[-1]; z=zipfile.ZipFile(p); print('\n'.join(z.namelist())); print(z.read('mnemox_control-0.2.0.dist-info/METADATA').decode())"
```

Verify only intended modules/metadata are present and metadata declares version 0.2.0, Python
>=3.12, and AGPL-3.0-only; do not infer success from build exit alone.

- [ ] **Step 4: Verify requirements line by line**

Re-read the approved spec Success Criteria and Implementation Boundaries. Record each satisfied
criterion and every deferred PEP item in `AGENTS.md`; do not call deferred authorization,
signature, reservation, execution, or completeness services implemented.

- [ ] **Step 5: Commit and push when possible**

Commit: `chore: complete evaluation kernel v0.2 release gate`

Run: `git remote -v`

If `origin` exists, run `git push -u origin feat/evaluation-kernel-v0.2`. If it does not exist,
record that exact blocker in `AGENTS.md` and preserve the branch locally.
