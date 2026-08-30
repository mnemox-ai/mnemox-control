# Mnemox Evaluation Protocol v0.2

Status: implemented kernel protocol. Protocol documents, schemas, and conformance vectors are
licensed under Apache-2.0. The Python reference engine is AGPL-3.0-only or separately commercially
licensed.

## Purpose and boundary

The Evaluation Kernel is a deterministic Policy Decision Point (PDP). It answers whether one
proposed `OrderIntent` is compatible with an owner policy and a complete trusted state snapshot.
It does not authenticate issuers, reserve risk capacity, issue a single-use authorization grant,
submit orders, reconcile broker state, or prove that every broker order passed through Mnemox.
Those are Policy Enforcement Point (PEP) and evidence-service responsibilities.

An `ALLOW` result is evidence from the static PDP. It is not permission to send an order directly
to a broker. A production gateway must later validate policy authority and freshness, atomically
reserve capacity, issue and consume a grant once, execute idempotently, and reconcile the result.

## Pure API

```python
evaluate(
    *,
    policy: PolicyBundle,
    intent: OrderIntent,
    account: TrustedAccountSnapshot,
    market: MarketSnapshot,
    instruments: InstrumentCatalog,
    evaluated_at: datetime,
) -> EvaluationResult
```

The function reads no clock, network, filesystem, broker credential, storage, UUID source, or
randomness. Equal canonical inputs produce byte-identical output. `evaluated_at` must be supplied
and timezone-aware.

## Canonical trust inputs

`PolicyBundle`, `TrustedAccountSnapshot`, `MarketSnapshot`, and `InstrumentCatalog` are trusted
roles and must carry a lowercase SHA-256 `content_hash` of their canonical content excluding the
hash field. Missing seals deny with `UNSEALED_TRUST_INPUT`; mismatches deny with `HASH_MISMATCH`.
This proves content integrity, not identity or authority. Issuer signatures and policy revocation
remain PEP concerns.

`OrderIntent` is untrusted and carries no claimed hash. The kernel always computes its hash. The
result binds the actual canonical hashes of all five inputs, account state version, and evaluation
time.

Canonical JSON uses UTF-8, sorted object keys, no insignificant whitespace, UTC `Z` timestamps,
plain decimal strings, lowercase SHA-256, and normalized enum values. Unknown wire enum values are
schema errors; recognized but unsupported products produce `UNSUPPORTED_INSTRUMENT`.

## Supported valuation

v0.2 supports `SPOT` and `LINEAR_PERPETUAL` in `ONE_WAY` mode. Inverse products, futures, options,
hedge-mode dual positions, cross-margin offsets, and multi-leg atomic strategies are represented
by the wire vocabulary but denied by this kernel.

Signed quantity is:

```text
BUY  = +quantity
SELL = -quantity
proposed_fill = current_position + signed_quantity
linear_notional = abs(quantity) × reference_price × contract_multiplier
```

MARKET BUY uses ask and MARKET SELL uses bid. LIMIT and STOP use their declared price. Exact
`Decimal` modulo validates quantity step and price tick; the engine never silently rounds an
intent.

For each symbol, pending BUY and SELL orders create independent envelopes:

```text
upper = current + sum(non-reduce-only BUY remaining quantity)
lower = current - sum(non-reduce-only SELL remaining quantity)
```

A non-reduce-only proposed order is added to its side. Opposing orders never cancel. Existing and
proposed reduce-only orders never reduce the capacity envelope because they may not fill. The
larger absolute envelope is valued with the instrument multiplier and the maximum of mark and
applicable executable/reference prices. Gross exposure sums every symbol without cross-symbol
netting. Missing catalog or quote coverage makes aggregate metrics undefined and denies.

## Strict reduce-only semantics

A reducer must carry `reduce_only=True`, start from non-zero exposure, use the opposite side,
strictly reduce absolute quantity, and never cross zero. Any existing non-terminal target-symbol
order makes the reducer uncertain and denies normal evaluation. Only a valid strict reducer can
receive `NEW_RISK_ONLY` exemptions.

`RECONCILE_REQUIRED` and `FULL_HALT_ACTIVE` are `NORMAL_PATH_BLOCKER` rules and deny even a strict
reducer on this API. A future emergency-flatten capability must be narrower and separately
authorized.

## Stable rule order

Every result contains exactly one rule result for every code in this order:

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

Rules return `PASS`, `DENY`, `ESCALATE`, or `SKIP`. A `SKIP` must name one or more prior rules that
actually denied, so missing calculations cannot masquerade as PASS. Decision precedence is:

```text
any DENY          -> DENY
else any ESCALATE -> ESCALATE
else              -> ALLOW
```

All triggered outcomes remain visible even when a stronger outcome determines the decision.
Maximum order quantity/notional, position notional, leverage, and open-order limits are inclusive;
only values above them deny. Daily loss and drawdown deny at their thresholds. Human approval
escalates at or above its threshold.

## Enforcement classes

- `ALWAYS`: integrity, binding, policy validity, freshness, coverage, increment, price collar, and
  reduce-only correctness rules always apply.
- `NEW_RISK_ONLY`: trading window, soft/reduce-only halt modes, allowlist, short/open-order/order/
  position/leverage/equity/loss/drawdown limits, and human approval are exempt only for a verified
  strict reducer.
- `NORMAL_PATH_BLOCKER`: reconciliation and full halt always deny this normal API.

The Python engine encodes one class for every reason code in `RULE_ENFORCEMENT`; no scattered
early-return exemption is authoritative.

## Temporal rules

Policy validity is half-open: `valid_from <= evaluated_at < expires_at`. Snapshot freshness is
inclusive at the configured maximum age, while future timestamps are distinct denials. The
trusted realized-P&L period must equal the UTC risk-day interval selected by
`risk_day_start_hour_utc` and contain `evaluated_at`. Weekly windows are sorted, non-overlapping,
and half-open in `[0, 10080)` UTC minutes.

## Conformance

Apache-licensed language-neutral vectors live in `tests/conformance/v0.2/`. Each vector contains
all inputs plus the complete JSON result, canonical JSON bytes rendered as UTF-8 text, and content
hash. A conforming implementation must reconstruct the models, evaluate them, and match all three
representations exactly. `tests/generate_conformance_vectors.py` prints reviewed candidate vectors;
updating fixtures requires code review because fixtures are protocol artifacts, not snapshots to
rewrite automatically during tests.

`DecisionReceipt` remains importable only for v0.1 compatibility. New integrations use
`EvaluationResult`; execution evidence will belong to a future `ExecutionReceipt`.
