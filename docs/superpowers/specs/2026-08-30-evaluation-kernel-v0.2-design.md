# Mnemox Evaluation Kernel v0.2 — Design

## Decision

Mnemox is not a trading signal system or a collection of configurable risk checks. It is a
broker-neutral authorization, enforcement, and evidence protocol for agentic trading.

This slice builds the deterministic Policy Decision Point (PDP). It deliberately does not claim
to be the Policy Enforcement Point (PEP), because non-bypassability, atomic exposure reservation,
credential custody, broker submission, and reconciliation require a later execution gateway.

The central artifact is a proof-carrying evaluation: a decision is valid only for one immutable
intent, policy revision, account-state version, market-state version, instrument definition, and
evaluation instant.

## Product Boundary and Defensibility

Mnemox uses a layered distribution model:

| Surface | Distribution | Purpose |
|---|---|---|
| Protocol specification, schemas, SDK, canonical encoding, verifier, conformance vectors | Apache-2.0 | Remove adoption friction and make independent verification possible |
| Community evaluation and gateway engine | AGPL-3.0 with a separate commercial license | Keep network-service modifications available while permitting commercial embedding under contract |
| Managed authorization service, trust registry, transparency log, official adapter certification, failure corpus, enterprise control plane | Proprietary service | Operate the authoritative trust and enforcement network |
| Mnemox name, marks, and “Mnemox Verified” claims | Trademark and certification policy | Prevent forks from implying official certification |

Open source code can be forked. Defensibility comes from official trust roots, conformance and
adapter certification, broker integrations, accumulated failure evidence, execution coverage,
distribution, and the managed enforcement footprint—not from intentionally obscure code.

No license metadata changes are made until implementation begins. Before any public release, the
repository must contain complete license texts, notices, contributor terms that preserve dual-
licensing rights, and a trademark policy reviewed by qualified counsel.

Within this repository, protocol documents, JSON schemas, and language-neutral conformance
vectors will be Apache-2.0. The installable Python engine will be AGPL-3.0 plus a commercial
license from Mnemox. An application that embeds the engine therefore receives the engine under
AGPL unless it obtains the commercial license; merely implementing the public protocol from the
Apache materials does not require the engine license. SPDX file headers and a root license map
make this boundary machine-readable.

## Evidence From Existing Mnemox Assets

This design extracts invariants rather than copying product-specific implementations:

- `ai-trading-desk-v2` already treats a timed-out order submission as ambiguous, assigns a unique
  client order identity, reconciles with Binance, handles partial fills, and reports naked
  exposure when both hedge and flatten fail.
- Its watchdog separates the slow strategy loop from fast reconciliation, treats an unavailable
  account state as a breach, detects missing protection, and maintains sticky halt states.
- `TradeMemory Protocol` already supplies deterministic content hashes, append-only chaining,
  daily Merkle roots, and timestamp anchoring. Its missing property for Control is completeness:
  a valid chain does not prove that every broker-side event was included.
- `NG_Gold` supplies account, portfolio, period-loss, and kill-switch concepts, but its policy is
  currently coupled to an EA and must become broker-neutral.
- VERIS supplies signed, expiring attestations and separation between a platform data domain and
  an independent issuer. Mnemox reuses that trust-boundary lesson for official certification.

## Threat Model

### Protected assets

- Broker credentials and the only path capable of increasing account risk.
- Owner-authored policy and its active revision.
- Accurate account, position, open-order, and market state.
- Exposure capacity reserved for concurrent agents.
- The causal link from intent through evaluation, authorization, execution, and reconciliation.
- Evidence completeness and the ability to detect unauthorized broker activity.

### Adversaries and failures

The design assumes any of the following can occur independently:

1. An Agent is malicious, compromised, buggy, or repeatedly retries an old intent.
2. An Agent fabricates balances, positions, market prices, timestamps, or policy contents.
3. A valid old policy is replayed after a stricter revision or revocation.
4. Two Agents evaluate against the same available exposure concurrently.
5. Clocks differ or state arrives out of order.
6. Market price moves between evaluation and broker acceptance.
7. Broker submission succeeds but its response is lost.
8. An order is partially filled while cancellation or replacement is in flight.
9. The local ledger and broker disagree after a crash.
10. A manual, alternate-API, or stolen-credential order bypasses Mnemox.
11. Evidence is modified, reordered, selectively omitted, or generated by an unofficial fork.
12. Mnemox, its state provider, evidence store, or broker API becomes unavailable.

### Explicit non-assumptions

- The Agent is never a trusted source of account or market state.
- A valid content hash does not establish identity, authority, freshness, completeness, or
  non-revocation.
- `ALLOW` does not prove execution safety and is not permission to call a broker.
- Exactly-once network delivery is not achievable by declaration.
- “Fail closed” does not mean blocking risk-reducing emergency actions.

## Trust Roles

### Policy owner

Defines policy, owns the signing identity, and can issue monotonically increasing revisions or
revocations. The owner cannot alter an already issued evaluation or execution record.

### Agent

May create an `OrderIntent` and inspect results. It cannot provide trusted account state, mint an
authorization, modify policy, reserve exposure, access broker credentials, or write official
evidence.

### State provider

Reads broker and market sources and emits versioned snapshots with provenance. In v0.2 the kernel
validates the snapshot shape and bindings; source authentication is deferred to the PEP slice.

### Evaluation kernel (PDP)

Pure deterministic code. It consumes explicit inputs and produces an `EvaluationResult`. It has
no clock, network, storage, randomness, credentials, or side effects.

### Execution gateway (PEP, future slice)

Owns credentials, verifies provenance and policy authority, atomically reserves exposure, mints a
single-use `AuthorizationGrant`, submits with idempotent broker identity, reconciles ambiguous
outcomes, and writes official lifecycle evidence.

### Verifier

Independently checks hashes, signatures, state bindings, chain inclusion, coverage statements,
and certification status. It never needs broker credentials.

## System Invariants

These invariants are normative for the target architecture. v0.2 implements the subset marked
`KERNEL`; the remainder shape future interfaces and prevent incompatible shortcuts.

1. **KERNEL — Determinism:** identical canonical inputs produce byte-identical evaluation output.
2. **KERNEL — Complete binding:** every result commits to policy, intent, account snapshot, market
   snapshot, instrument specification, and evaluation time.
3. **KERNEL — Fail-safe increase:** unknown, stale, inconsistent, or unsupported inputs cannot
   authorize increased risk.
4. **KERNEL — Reduce-only monotonicity:** a reduce-only intent must strictly lower absolute
   position size and may not cross zero.
5. **KERNEL — Pending exposure counts:** projected exposure includes live positions and all
   accepted but non-terminal order quantities represented by the snapshot.
6. **KERNEL — Worst applicable outcome:** hard denial outranks escalation; escalation outranks
   allow. All triggered rules remain visible even when a higher-severity rule determines the
   decision.
7. **PEP — No authorization, no execution:** every risk-increasing broker order maps to one valid
   official grant.
8. **PEP — Single use:** a grant can transition from available to consumed or expired only once.
9. **PEP — Atomic capacity:** exposure capacity reservation and grant issuance are one atomic
   state transition.
10. **PEP — At-most-once risk authorization:** retries reuse a stable intent identity and cannot
    reserve exposure twice.
11. **PEP — Ambiguity is a state:** transport failure after submission becomes `UNKNOWN`, not
    `REJECTED`; no retry occurs before reconciliation.
12. **PEP — Broker is economic truth:** fills and positions come from the broker; Mnemox records
    authorization and expected process state. A disagreement causes a sticky breach.
13. **PEP — Emergency asymmetry:** uncertain state prohibits new risk but may permit a separately
    verified reduce-only or emergency-flatten path.
14. **EVIDENCE — Causal completeness:** every official broker order and fill must be covered by an
    authorization lineage or recorded as an unauthorized-activity breach.
15. **EVIDENCE — Tamper and omission visibility:** content integrity, sequence continuity, broker
    coverage, and periodic signed roots are separate proofs.

## Supported Trading Semantics

v0.2 supports exactly:

- `SPOT` with signed base-asset quantity represented in one net position.
- `LINEAR_PERPETUAL` with `ONE_WAY` position mode and linear quote-currency notional.

It rejects:

- inverse contracts;
- options;
- hedge-mode dual positions;
- portfolio/cross-margin offsets;
- multi-leg atomic strategies;
- unrecognized instrument types or notional models.

Unsupported products fail with a stable `UNSUPPORTED_INSTRUMENT` reason instead of reusing an
incorrect linear formula.

## Domain Contracts

All contracts inherit the existing strict, frozen, unknown-field-rejecting model. Timestamps are
timezone-aware and normalized to UTC. Quantities, prices, multipliers, and money use `Decimal`.

### `InstrumentSpec`

Fields:

- `instrument_id: str`
- `version: str`
- `broker: str`
- `symbol: str`
- `instrument_type: SPOT | LINEAR_PERPETUAL`
- `position_mode: ONE_WAY`
- `allows_short: bool`
- `base_asset: str`
- `quote_asset: str`
- `contract_multiplier: Decimal`
- `quantity_step: Decimal`
- `price_tick: Decimal`
- `min_quantity: Decimal`
- `min_notional: Decimal`

Linear notional:

```text
abs(quantity) × reference_price × contract_multiplier
```

The kernel rejects values that do not align to quantity step or price tick. It does not silently
round an Agent's request because rounding changes the signed intent.

### `InstrumentCatalog`

Fields:

- `catalog_id: UUID`
- `version: str`
- `broker: str`
- `instruments: tuple[InstrumentSpec, ...]`
- `observed_at: datetime`
- `content_hash: str | None`

Symbols and instrument IDs are unique. Every position, non-terminal order, and proposed intent
must resolve to exactly one supported specification. `SPOT` normally sets `allows_short=False`;
`LINEAR_PERPETUAL` may allow short exposure. A projected negative position on an instrument that
forbids shorts is DENY.

### `Position`

Fields:

- `symbol: str`
- `signed_quantity: Decimal`

Positive quantity is long, negative quantity is short, and zero is flat.
Positions contain at most one entry per symbol. Duplicate symbols make the snapshot structurally
invalid.

### `OpenOrderExposure`

Fields:

- `broker_order_id: str`
- `intent_id: UUID | None`
- `symbol: str`
- `side: BUY | SELL`
- `remaining_quantity: Decimal`
- `reduce_only: bool`
- `reference_price: Decimal`
- `status: NEW | PARTIALLY_FILLED | PENDING_CANCEL | UNKNOWN`

Every non-terminal order counts toward projected worst-case exposure. `UNKNOWN` counts in full.
Broker order IDs are unique within a snapshot, remaining quantity and reference price are
strictly positive, and duplicate IDs invalidate the snapshot.

### `TrustedAccountSnapshot`

Fields:

- `snapshot_id: UUID`
- `state_version: int`
- `source: str`
- `account_id: str`
- `broker: str`
- `equity: Decimal`
- `cash_balance: Decimal`
- `realized_pnl_today: Decimal`
- `realized_pnl_period_start: datetime`
- `realized_pnl_period_end: datetime`
- `drawdown_from_peak: Decimal`
- `positions: tuple[Position, ...]`
- `open_orders: tuple[OpenOrderExposure, ...]`
- `halt_state: NORMAL | SOFT_HALT | REDUCE_ONLY | FULL_HALT | RECONCILE_REQUIRED`
- `observed_at: datetime`
- `content_hash: str | None`

`state_version` must be positive and monotonic at the provider boundary. The pure kernel can bind
to a version but cannot prove global monotonicity without storage; that responsibility belongs to
the future gateway.

`realized_pnl_today` is signed: profit is positive, loss is negative. `drawdown_from_peak` is a
non-negative amount. Deposits and withdrawals must already be reflected by the trusted provider's
peak-equity methodology.

The realized-P&L window is half-open and must contain `evaluated_at`. Its UTC boundary must match
the policy's configured risk-day start. This prevents different brokers from silently interpreting
“today” with different time zones or reset times.

### `MarketQuote`

Fields:

- `symbol: str`
- `bid: Decimal`
- `ask: Decimal`
- `mark: Decimal`

Rules require `0 < bid <= ask` and a positive mark.

### `MarketSnapshot`

Fields:

- `snapshot_id: UUID`
- `source: str`
- `quotes: tuple[MarketQuote, ...]`
- `observed_at: datetime`
- `content_hash: str | None`

Quote symbols are unique. Every position, non-terminal order, and proposed intent must have a
quote. This makes account-wide exposure computable instead of valuing only the proposed symbol.

### `RuleResult`

Fields:

- `code: ReasonCode`
- `outcome: PASS | ESCALATE | DENY | SKIP`
- `actual: Decimal | str | bool | None`
- `limit: Decimal | str | bool | None`
- `blocked_by: tuple[ReasonCode, ...]`
- `subjects: tuple[str, ...]`

Messages are not part of the canonical decision protocol. Stable codes and structured actual/
limit values allow localization without changing hashes.

Rules that aggregate multiple failures, such as hash or binding mismatches, list deterministic
sorted field paths in `subjects` rather than emitting a variable number of repeated reason codes.

### `EvaluationResult`

Fields:

- `protocol_version: Literal["0.2"]`
- `decision: ALLOW | DENY | ESCALATE`
- `policy_hash: str`
- `intent_hash: str`
- `account_snapshot_hash: str`
- `market_snapshot_hash: str`
- `instrument_catalog_hash: str`
- `account_state_version: int`
- `evaluated_at: datetime`
- `reference_price: Decimal | None`
- `order_notional: Decimal | None`
- `current_position_quantity: Decimal | None`
- `proposed_fill_position_quantity: Decimal | None`
- `worst_case_position_quantity: Decimal | None`
- `worst_case_position_notional: Decimal | None`
- `projected_gross_exposure: Decimal | None`
- `projected_leverage: Decimal | None`
- `position_effect: OPEN | INCREASE | REDUCE | CLOSE | REVERSE | None`
- `rules: tuple[RuleResult, ...]`
- `content_hash: str | None`

`EvaluationResult` replaces the decision portion of v0.1 `DecisionReceipt`. It cannot contain a
broker order ID. Execution evidence will move to a separate future `ExecutionReceipt`.

Derived metrics are `None` only when a prior integrity, binding, or instrument rule makes the
calculation undefined. Dependent rules then emit `SKIP` with `blocked_by`; they never emit a
fabricated PASS. A SKIP is valid only when at least one blocking rule emitted DENY, so it cannot
produce an ALLOW through missing evaluation.

## Required Policy v0.2 Additions

`PolicyBundle` gains:

- `revision: int`
- `previous_policy_hash: str | None`
- `max_state_age_seconds: int`
- `max_market_age_seconds: int`
- `max_instrument_age_seconds: int`
- `max_price_deviation_bps: Decimal`
- `max_open_orders: int`
- `max_order_quantity: Decimal | None`
- `allow_position_reversal: bool`
- `risk_day_start_hour_utc: int`
- `allowed_weekly_windows: tuple[WeeklyWindow, ...]`

Policy signing, revocation lookup, and minimum accepted revision are PEP concerns and remain out of
the pure kernel. The kernel validates structural revision and hash linkage only.

`WeeklyWindow` uses `start_minute_utc` and `end_minute_utc` in the half-open range of a UTC week
(`0 <= start < end <= 10080`). Windows are sorted, non-overlapping, and non-empty; a 24/7 policy
uses one `[0, 10080)` window. `risk_day_start_hour_utc` is an integer from 0 through 23.

All maximum monetary/exposure limits and `max_order_quantity`, when present, are strictly
positive. `max_open_orders` is non-negative. `approval_notional` remains non-negative: zero
intentionally escalates every otherwise valid risk-increasing order.

Policy `revision` starts at 1. Revision 1 requires `previous_policy_hash=None`; every later
revision requires a valid previous hash. The kernel validates this shape but cannot prove that the
referenced policy was the account's immediately preceding active revision; the future policy
registry enforces that monotonic transition and revocation state.

## Evaluation Inputs and API

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
    ...
```

The function never generates time, UUIDs, or randomness. All model inputs are canonicalized and
hashed before rules run. Policy, account, market, and instrument catalog are trust-bearing inputs and must
carry a valid content hash; absence denies with `UNSEALED_TRUST_INPUT`, while a claimed/recomputed
disagreement denies with `HASH_MISMATCH`. `OrderIntent` is untrusted input and carries no claimed
hash; the kernel always computes its hash. `evaluated_at` is a bound scalar, not a sealed model.

In v0.2, “trusted” means the snapshot occupies the trusted input role and is hash-bound. It does
not mean cryptographically authenticated. The gateway must later verify its issuer signature.

## Position and Exposure Semantics

Signed order quantity:

```text
BUY  → +quantity
SELL → -quantity
```

For the target symbol:

```text
current_quantity = broker position signed quantity
proposed_fill_quantity = current_quantity + proposed_signed_quantity
```

For `reduce_only=True`:

```text
current_quantity != 0
sign(proposed_signed_quantity) == -sign(current_quantity)
abs(proposed_fill_quantity) < abs(current_quantity)
sign(proposed_fill_quantity) is sign(current_quantity) or proposed_fill_quantity is zero
```

If any non-terminal order already exists for the target symbol, a new reduce-only intent is DENY
with `REDUCE_ONLY_UNCERTAIN`. v0.2 does not guess the fill ordering of multiple reducers.

The kernel classifies the direct current-to-proposed transition:

```text
flat to non-zero                         → OPEN
same sign and greater absolute quantity → INCREASE
same sign and lower absolute quantity   → REDUCE
non-zero to zero                         → CLOSE
sign changes across zero                 → REVERSE
```

`REVERSE` is denied unless `allow_position_reversal` is true. Only an intent carrying
`reduce_only=True` and satisfying the monotonicity rules receives exemptions reserved for
risk-reducing actions. An ordinary opposite-side order is not trusted as a reducer even when its
requested quantity appears smaller than the current position.

Opposing non-terminal orders must not cancel each other in risk math: a BUY and SELL can fill at
different times. For each symbol, construct a conservative position envelope using only
risk-increasing non-reduce-only remaining quantities:

```text
upper_quantity = current_quantity + sum(all remaining BUY quantities)
lower_quantity = current_quantity - sum(all remaining SELL quantities)

for the proposed risk-increasing intent:
    add its quantity to upper_quantity when BUY
    subtract its quantity from lower_quantity when SELL

worst_case_position_quantity = whichever of upper_quantity or lower_quantity
                               has the greater absolute value
```

Existing reduce-only orders do not reduce worst-case exposure because they may not fill. A valid
proposed reduce-only intent reports its specific `proposed_fill_position_quantity`, but it also
does not reduce the account's conservative exposure envelope for capacity purposes.

Projected gross exposure is the sum of each symbol's worst-case absolute notional. Opposing
symbols, sides, or strategies are not netted in v0.2. Each symbol uses its catalog multiplier and
current market mark. For a proposed or pending order, valuation uses the more conservative of the
current mark and the order's executable/reference price (`max(mark, reference_price)`). Missing
catalog or market coverage makes aggregate metrics undefined and DENY; the
kernel never drops an unvalued position from the sum.

```text
projected_leverage = projected_gross_exposure / equity
```

Non-positive equity denies all new risk. A verified reduce-only intent can still pass the static
kernel when it strictly reduces absolute exposure, but the future gateway controls whether its
emergency path is operationally available.

## Reference Price and Price Collar

- MARKET uses the adverse side: ask for BUY, bid for SELL.
- LIMIT and STOP use their declared price for notional, but price-collar comparison uses mark.
- MARKET compares its adverse-side reference price with mark for the same collar.
- BUY deviation is `(order_price - mark) / mark` when above mark.
- SELL deviation is `(mark - order_price) / mark` when below mark.
- A deviation beyond `max_price_deviation_bps` denies the intent.

The first slice does not predict slippage or market impact. Those belong to broker-specific
execution policy and later calibration.

## Rule Order and Stable Reason Codes

Rules execute in a fixed protocol order so canonical results are reproducible. Every rule emits
exactly one `RuleResult`; evaluation does not stop at the first failure. A rule whose required
metric is undefined emits `SKIP` and names the DENY prerequisites in `blocked_by`.

Order:

1. `UNSEALED_TRUST_INPUT`
2. `HASH_MISMATCH`
3. `BINDING_MISMATCH`
4. `UNSUPPORTED_INSTRUMENT`
5. `POLICY_NOT_YET_ACTIVE`
6. `POLICY_EXPIRED`
7. `ACCOUNT_STATE_FROM_FUTURE`
8. `ACCOUNT_STATE_STALE`
9. `MARKET_STATE_FROM_FUTURE`
10. `MARKET_STATE_STALE`
11. `INSTRUMENT_STATE_FROM_FUTURE`
12. `INSTRUMENT_STATE_STALE`
13. `INSTRUMENT_COVERAGE_MISSING`
14. `MARKET_COVERAGE_MISSING`
15. `PNL_WINDOW_MISMATCH`
16. `OUTSIDE_TRADING_WINDOW`
17. `RECONCILE_REQUIRED`
18. `SOFT_HALT_ACTIVE`
19. `FULL_HALT_ACTIVE`
20. `REDUCE_ONLY_MODE`
21. `SYMBOL_NOT_ALLOWED`
22. `INVALID_INCREMENT`
23. `PRICE_COLLAR_EXCEEDED`
24. `REDUCE_ONLY_VIOLATION`
25. `REDUCE_ONLY_UNCERTAIN`
26. `POSITION_REVERSAL_FORBIDDEN`
27. `SHORT_POSITION_FORBIDDEN`
28. `OPEN_ORDER_LIMIT_EXCEEDED`
29. `ORDER_QUANTITY_EXCEEDED`
30. `ORDER_NOTIONAL_EXCEEDED`
31. `POSITION_NOTIONAL_EXCEEDED`
32. `LEVERAGE_EXCEEDED`
33. `NON_POSITIVE_EQUITY`
34. `DAILY_LOSS_LIMIT_REACHED`
35. `DRAWDOWN_LIMIT_REACHED`
36. `HUMAN_APPROVAL_REQUIRED`

Precedence:

```text
any DENY     → DENY
else any ESCALATE → ESCALATE
else              → ALLOW
```

`SKIP` does not participate in precedence and is forbidden unless a listed blocking rule denied
the evaluation.

`HUMAN_APPROVAL_REQUIRED` is ESCALATE. Every other triggered violation above is DENY. In halt or
loss-limit states, a strictly exposure-reducing intent is exempt only from rules explicitly
classified as “new-risk blockers”; it is never exempt from binding, integrity, instrument, stale
market, price-increment, or reduce-only correctness rules.

The exemption matrix is normative and must be encoded as data, not scattered as early returns:

| Rule group | Valid strict reduce-only intent | Other intent |
|---|---:|---:|
| Integrity, hash, binding, supported instrument, policy validity, snapshot freshness, P&L window, increment, price collar | Enforce | Enforce |
| `RECONCILE_REQUIRED`, `FULL_HALT_ACTIVE` | Deny normal evaluation; future emergency path is separate | Deny |
| Trading window, `SOFT_HALT_ACTIVE`, `REDUCE_ONLY_MODE`, symbol allowlist, open-order, order quantity/notional, position notional, leverage, non-positive equity, daily loss, drawdown | Exempt | Enforce |
| Reduce-only correctness and uncertainty | Enforce | Not applicable after intent classification |
| Position reversal | Impossible for valid reduce-only | Enforce policy |
| Human approval threshold | Exempt | Escalate at threshold |

An allowlist removal therefore prevents new exposure but does not trap a verified existing
position. A full halt or reconciliation breach cannot be bypassed by presenting an ordinary
reduce-only intent; the later PEP owns a narrower emergency-flatten capability.

Numeric thresholds are inclusive: equality at maximum order quantity, maximum order notional,
maximum position notional, maximum leverage, and maximum open orders passes; exceeding them
denies. The proposed order counts when comparing `len(open_orders) + 1` with `max_open_orders`.
Daily loss denies when `realized_pnl_today <= -max_daily_loss`. Drawdown denies when
`drawdown_from_peak >= max_drawdown`. Human approval escalates when order notional is greater than
or equal to `approval_notional`, provided no DENY rule applies.

## Temporal Semantics

Freshness is evaluated only against caller-supplied `evaluated_at`:

```text
0 <= evaluated_at - observed_at <= max_age
```

A snapshot in the future is a distinct denial, not fresh data. Equality at the age limit passes.
Policy validity is half-open:

```text
valid_from <= evaluated_at < expires_at
```

An evaluation is historical evidence, not a reusable capability. The future grant will have its
own short expiry and state-version binding.

## Evaluation Versus Authorization

v0.2 stops after `EvaluationResult`. A caller must not submit to a broker based on this result
alone.

The next PEP slice will introduce:

```text
EvaluationResult(ALLOW)
  → compare-and-swap account_state_version
  → atomically reserve worst-case exposure
  → AuthorizationGrant(intent_hash, all state hashes, reservation_id, expires_at, nonce)
  → mark grant consumed before/idempotently with submission
  → reconcile to terminal broker outcome
```

This separation prevents a pure evaluator from falsely claiming concurrency safety.

## Future Execution State Machine

The following states are reserved now so v0.2 does not overload decision records:

```text
INTENT_RECEIVED
EVALUATED_DENY | EVALUATED_ESCALATE | EVALUATED_ALLOW
RESERVED
SUBMITTING
ACKNOWLEDGED | REJECTED | UNKNOWN
PARTIALLY_FILLED
FILLED | CANCELED | EXPIRED
RECONCILE_REQUIRED
RECONCILED
BREACH
```

`UNKNOWN` is non-terminal. No new submission using the same authorization is allowed until broker
query or event-stream reconciliation resolves it.

## Evidence Model

Three independent claims must never be conflated:

1. **Integrity:** canonical hash and chain linkage show recorded contents were not silently
   modified.
2. **Authenticity:** issuer signatures identify the authority that created policy, state,
   authorization, execution, and certification records.
3. **Completeness:** broker order/fill coverage and continuous sequence commitments expose omitted
   or bypassed activity.

The later evidence plane will periodically commit:

- official authorization IDs;
- broker client-order IDs and exchange order IDs;
- fill and position sequence ranges;
- unauthorized-order breaches;
- missing-data intervals;
- adapter and method versions;
- Merkle root, previous root, issuer signature, and external timestamp anchor.

A fork can generate its own evidence but cannot claim Mnemox issuance or official adapter
certification without the Mnemox trust root.

## Failure Matrix

| Condition | Kernel result | Future gateway action |
|---|---|---|
| Agent sends malformed or unsealed input | DENY | Record no-trade evidence |
| Trusted state unavailable | No evaluation | Freeze new risk; preserve emergency reduce path |
| Snapshot stale or from future | DENY | Refresh; do not reserve |
| Account version changes before reservation | Prior result obsolete | Re-evaluate against new state |
| Capacity reservation conflict | Evaluation remains historical | Reject/retry evaluation; do not mint grant |
| Broker POST times out | Not a kernel concern | State UNKNOWN; reconcile by stable client ID |
| Partial fill during cancel | Not a kernel concern | Update exposure from cumulative fill; reconcile residual |
| Broker/local position mismatch | DENY new risk | Sticky RECONCILE_REQUIRED; alert and reconcile |
| Full halt | DENY new risk | Cancel entries; allow verified reduce/flatten workflow |
| Evidence store unavailable | Not a kernel concern | No new-risk execution; emergency actions buffered and later anchored |

## Testing Strategy

### Example tests

- Every binding mismatch produces DENY.
- MARKET BUY uses ask and MARKET SELL uses bid.
- LIMIT/STOP price collars are side-aware.
- Long increase, long reduction, long-to-short crossing, short increase, short reduction, and
  short-to-long crossing have explicit cases.
- Pending NEW, PARTIALLY_FILLED, PENDING_CANCEL, and UNKNOWN exposure counts at worst case.
- Policy and snapshot time boundaries are exact.
- All rules execute and retain evidence despite earlier failures.
- Reason ordering and canonical hashes are stable.

### Property tests

- Increasing order quantity cannot lower projected gross exposure for a risk-increasing intent.
- Adding a non-terminal pending order cannot increase available capacity.
- A valid reduce-only order strictly lowers absolute position quantity and never crosses zero.
- Changing any bound input changes the result content hash.
- Reordering input mappings does not change canonical output.
- Any DENY rule forces the final decision to DENY regardless of ESCALATE rules.
- Evaluation does not mutate any input.

Property tests use deterministic generated values and persist minimal failing examples in the test
runner's normal cache only; no production randomness enters evaluation.

### Conformance vectors

Publish language-neutral JSON fixtures containing canonical inputs, expected rule results,
computed metrics, and expected hashes. A third-party implementation is protocol-compatible only
if every vector matches byte-for-byte.

## Implementation Boundaries

v0.2 includes:

- the new domain contracts;
- PolicyBundle v0.2 fields;
- deterministic evaluation and calculations;
- stable reasons and rule evidence;
- example, boundary, property, and conformance tests;
- migration notes for v0.1 `DecisionReceipt` users;
- license-boundary documentation.

v0.2 excludes:

- signature implementation and key storage;
- revocation service;
- reservation database;
- AuthorizationGrant minting;
- broker credentials or network calls;
- order submission and execution state persistence;
- reconcile/watchdog extraction;
- transparency-log service;
- official certification service;
- multi-asset margin offsets, correlation, VaR, options Greeks, and strategy quality scoring.

These exclusions are not considered safe by default; they are explicitly outside the claim of the
kernel. Documentation and package metadata must say that v0.2 cannot authorize or execute live
trades on its own.

## Success Criteria

The slice is successful when:

1. A strategy can submit a realistic intent plus deterministic paper-state inputs and receive a
   fully bound, replayable result.
2. The test suite proves position direction, pending exposure, freshness, binding, halt, limit,
   escalation, and fail-safe invariants.
3. Conformance fixtures allow another language to reproduce canonical hashes and outcomes.
4. No API implies that `ALLOW` is a broker authorization.
5. No production code reads time, randomness, network, storage, environment credentials, or
   broker state.
6. The design leaves an explicit seam for atomic reservation and execution reconciliation without
   changing evaluation semantics.

## Source References

- Local: `ai-trading-desk-v2/trader_v2.py`, `risk_watchdog.py`,
  `live_orchestrator.py`, and `docs/portfolio-design.md`.
- Local: `tradememory-protocol/src/tradememory/audit/chain.py` and audit tests.
- Local: `NG_Gold` account-risk, breaker, and decision-log assets.
- Local: `otso-risk-demo/engine/signing.py` and neutral-domain architecture decisions.
- FIX Trading Community, Order State Changes.
- FIA, Best Practices for Automated Trading Risk Controls and System Safeguards, July 2024.
- SEC Rule 15c3-5 market-access risk-control guidance.
- NIST SP 800-207 and the Policy Enforcement Point definition.
