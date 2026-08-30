# Mnemox Control Contracts v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build immutable, deterministic wire contracts for policies, proposed orders, and gateway decisions.

**Architecture:** A dependency-light Python package uses Pydantic v2 for strict validation and a shared canonical JSON module for stable hashing. Models never generate time or randomness, making fixtures and cross-system verification reproducible.

**Tech Stack:** Python 3.12+, Pydantic 2, pytest, Ruff, mypy, hatchling.

**Spec:** `docs/superpowers/specs/2026-08-30-contracts-v0.1-design.md`

## Global Constraints

- No broker, network, database, credential, or signature implementation in this slice.
- No production behavior without a failing test observed first.
- All models reject unknown fields and are frozen after construction.
- Timestamps normalize to UTC; decimals serialize as strings; hashes use lowercase SHA-256 hex.
- Tests must not depend on wall-clock time, randomness, external services, or environment secrets.

---

### Task 1: Project Skeleton and Canonical Serialization

**Files:**
- Create: `pyproject.toml`
- Create: `src/mnemox_control/__init__.py`
- Create: `src/mnemox_control/canonical.py`
- Test: `tests/test_canonical.py`

**Interfaces:**
- Consumes: Pydantic `BaseModel` instances.
- Produces: `canonical_json_bytes(model: BaseModel, *, exclude: set[str] | None = None) -> bytes`, `content_sha256(model: BaseModel, *, exclude: set[str] | None = None) -> str`.

- [ ] **Step 1: Write failing canonical serialization tests**

```python
class Fixture(BaseModel):
    amount: Decimal
    occurred_at: datetime

def test_canonical_json_normalizes_decimal_and_utc_timestamp() -> None:
    fixture = Fixture(amount=Decimal("10.5000"), occurred_at=datetime(2026, 8, 30, 8, tzinfo=timezone.utc))
    assert canonical_json_bytes(fixture) == b'{"amount":"10.5","occurred_at":"2026-08-30T08:00:00Z"}'
```

- [ ] **Step 2: Run `python -m pytest tests/test_canonical.py -q` and confirm import failure**

- [ ] **Step 3: Implement recursive normalization, compact sorted JSON, and SHA-256**

```python
def canonical_json_bytes(model: BaseModel, *, exclude: set[str] | None = None) -> bytes:
    data = model.model_dump(mode="python", exclude=exclude or set())
    normalized = _normalize(data)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

- [ ] **Step 4: Run canonical tests and confirm they pass**
- [ ] **Step 5: Commit `feat: add deterministic canonical serialization`**

### Task 2: PolicyBundle

**Files:**
- Create: `src/mnemox_control/contracts.py`
- Test: `tests/test_policy_bundle.py`

**Interfaces:**
- Consumes: caller-supplied UUIDs, UTC-aware timestamps, Decimal limits.
- Produces: `PolicyBundle` and `PolicyBundle.with_content_hash() -> PolicyBundle`.

- [ ] **Step 1: Write failing tests for normalization, validation, immutability, and content hashing**

```python
def test_policy_normalizes_symbols_and_hashes_without_mutation(valid_policy_data: dict[str, object]) -> None:
    policy = PolicyBundle(**valid_policy_data, allowed_symbols=(" btcusdt ", "ETHUSDT", "BTCUSDT"))
    hashed = policy.with_content_hash()
    assert policy.allowed_symbols == ("BTCUSDT", "ETHUSDT")
    assert policy.content_hash is None
    assert hashed.content_hash == content_sha256(policy, exclude={"content_hash"})

def test_policy_rejects_approval_above_order_limit(valid_policy_data: dict[str, object]) -> None:
    valid_policy_data["approval_notional"] = Decimal("1001")
    with pytest.raises(ValidationError, match="approval_notional"):
        PolicyBundle(**valid_policy_data)
```
- [ ] **Step 2: Run `python -m pytest tests/test_policy_bundle.py -q` and confirm missing model failure**
- [ ] **Step 3: Implement `StrictFrozenModel` and `PolicyBundle` with Pydantic field/model validators**
- [ ] **Step 4: Run policy tests and full canonical tests**
- [ ] **Step 5: Commit `feat: define immutable policy bundle contract`**

### Task 3: OrderIntent

**Files:**
- Modify: `src/mnemox_control/contracts.py`
- Test: `tests/test_order_intent.py`

**Interfaces:**
- Consumes: agent-proposed order data.
- Produces: `OrderIntent`, suitable for `content_sha256(intent)`.

- [ ] **Step 1: Write failing tests for MARKET/LIMIT/STOP price semantics, positive quantities, uppercase symbols, blank identities, and immutability**

```python
def test_limit_order_requires_limit_price(valid_intent_data: dict[str, object]) -> None:
    valid_intent_data["order_type"] = "LIMIT"
    with pytest.raises(ValidationError, match="limit_price"):
        OrderIntent(**valid_intent_data)

def test_market_order_rejects_price_fields(valid_intent_data: dict[str, object]) -> None:
    valid_intent_data["limit_price"] = Decimal("100")
    with pytest.raises(ValidationError, match="MARKET"):
        OrderIntent(**valid_intent_data)

def test_order_intent_hash_is_stable(valid_intent_data: dict[str, object]) -> None:
    left = OrderIntent(**valid_intent_data)
    right = OrderIntent(**dict(reversed(list(valid_intent_data.items()))))
    assert content_sha256(left) == content_sha256(right)
```
- [ ] **Step 2: Run `python -m pytest tests/test_order_intent.py -q` and confirm missing model failure**
- [ ] **Step 3: Implement enums and `OrderIntent` validators with no evaluation logic**
- [ ] **Step 4: Run order tests and the full suite**
- [ ] **Step 5: Commit `feat: define agent order intent contract`**

### Task 4: DecisionReceipt

**Files:**
- Modify: `src/mnemox_control/contracts.py`
- Modify: `src/mnemox_control/__init__.py`
- Test: `tests/test_decision_receipt.py`

**Interfaces:**
- Consumes: IDs and content hashes from a policy and order intent plus a gateway decision.
- Produces: `DecisionReceipt` and `DecisionReceipt.with_content_hash() -> DecisionReceipt`.

- [ ] **Step 1: Write failing tests for hash format, reason normalization, deny/escalate broker-ID prohibition, allow behavior, immutability, and content hashing**

```python
def test_deny_receipt_normalizes_reasons_and_disallows_broker_order(valid_receipt_data: dict[str, object]) -> None:
    valid_receipt_data.update(decision="DENY", reason_codes=(" leverage_limit ", "LEVERAGE_LIMIT"), broker_order_id="123")
    with pytest.raises(ValidationError, match="broker_order_id"):
        DecisionReceipt(**valid_receipt_data)

def test_deny_requires_reason_code(valid_receipt_data: dict[str, object]) -> None:
    valid_receipt_data.update(decision="DENY", reason_codes=())
    with pytest.raises(ValidationError, match="reason_codes"):
        DecisionReceipt(**valid_receipt_data)

def test_receipt_hash_excludes_content_hash(valid_receipt_data: dict[str, object]) -> None:
    receipt = DecisionReceipt(**valid_receipt_data)
    hashed = receipt.with_content_hash()
    assert hashed.content_hash == content_sha256(receipt, exclude={"content_hash"})
```
- [ ] **Step 2: Run `python -m pytest tests/test_decision_receipt.py -q` and confirm missing model failure**
- [ ] **Step 3: Implement `Decision`, `DecisionReceipt`, validators, and public exports**
- [ ] **Step 4: Run the complete test suite**
- [ ] **Step 5: Commit `feat: define verifiable decision receipt contract`**

### Task 5: Package Verification and Documentation

**Files:**
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `tasks.txt`

**Interfaces:**
- Consumes: all contracts from Tasks 1–4.
- Produces: documented public API and reproducible verification commands.

- [ ] **Step 1: Document the security boundary and a complete construction/hash example**
- [ ] **Step 2: Run `python -m pytest -q`, `python -m ruff check .`, and `python -m mypy src`**
- [ ] **Step 3: Build with `python -m build` and inspect the wheel contents**
- [ ] **Step 4: Update AGENTS.md Recent Changes and Current Status with exact verification evidence**
- [ ] **Step 5: Commit `docs: document contracts v0.1 package` and push**
