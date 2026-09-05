# Mnemox Evaluation Protocol v0.3

Status: implemented kernel protocol. Supersedes v0.2. Protocol documents, schemas, and conformance
vectors are licensed under Apache-2.0. The Python reference engine is AGPL-3.0-only or separately
commercially licensed.

This document states the delta from [v0.2](evaluation-v0.2.md). Everything not listed here is
unchanged, and the v0.2 document remains the reference for it: the purpose and boundary, the pure
API, the trusted-state requirements, determinism, and the meaning of an `ALLOW` result.

## Why v0.3 exists

v0.2 could express a stop order but could not express the requirement to have one. An owner could
cap notional, leverage, quantity and symbol, and still had no way to say the one thing that most
directly bounds a loss: that this agent may not open a position it has not protected.

The gap mattered because the surrounding system enforces what the policy states. An agent that
declares a stop in its own reasoning, with nothing in the policy requiring it, is protected only
for as long as the agent chooses to be.

## Breaking changes

v0.3 is a breaking change. A v0.2 `PolicyBundle` does not validate under v0.3, and every policy
content hash changes.

- `PolicyBundle.version` is now `"0.3"`.
- `PolicyBundle.require_protective_stop` is **required, with no default**. Defaulting it to false
  would silently give a policy author who has not heard of the field no protection at all;
  defaulting it to true would change what an existing policy means without anyone saying so.
  Requiring it forces the decision to be made once, explicitly, by whoever writes the policy.
- The reason-code vocabulary grows from 36 to 40. The order of existing codes is unchanged and the
  four new codes are inserted after `PRICE_COLLAR_EXCEEDED`.

Conformance vectors for v0.3 are published under `tests/conformance/v0.3/`. The v0.2 vectors remain
in the repository for anyone still on that version; they do not validate against a v0.3 engine, by
construction.

## New policy fields

```python
require_protective_stop: bool  # required
max_stop_distance_bps: int | None = None  # positive when present
min_stop_distance_bps: int | None = None  # positive when present
```

`min_stop_distance_bps` must be strictly below `max_stop_distance_bps` when both are present.

Both bounds are optional because an owner may reasonably decline to constrain distance while still
requiring that a stop exists. When a bound is absent it is not evaluated.

## New intent field

```python
protective_stop_price: Decimal | None = None
```

This is distinct from `stop_price`. `stop_price` is what makes an order a stop order.
`protective_stop_price` is the price at which an **entry** should be protected, and it makes the
protection part of the decision being authorized rather than a follow-up action that may never
happen.

It is refused on a `STOP` order, because a stop protecting a stop has no defined semantics here,
and on any `reduce_only` order, because an order that can only shrink exposure has nothing to
protect.

## New reason codes

| Code | Raised when |
|---|---|
| `PROTECTIVE_STOP_REQUIRED` | the policy requires a protective stop and a non-reduce-only intent carries none |
| `PROTECTIVE_STOP_WRONG_SIDE` | the stop is at or beyond the reference price on the wrong side: at or above it for a buy, at or below it for a sell |
| `PROTECTIVE_STOP_TOO_FAR` | the distance from the reference price exceeds `max_stop_distance_bps` |
| `PROTECTIVE_STOP_TOO_CLOSE` | the distance is below `min_stop_distance_bps` |

All four are `NEW_RISK_ONLY`. An order that can only reduce exposure is not the thing these guard
against, so a valid strict reducer passes them.

Distance is measured in basis points from the same reference price the rest of the evaluation uses,
so a stop is judged against the price the order would actually receive rather than against a
separate notion of "current price". The bounds are inclusive: a stop exactly at
`min_stop_distance_bps` passes, and one exactly at `max_stop_distance_bps` passes.

`PROTECTIVE_STOP_WRONG_SIDE` is evaluated before the distance bounds, and a wrong-sided stop is not
also reported as too far or too close. Reporting a distance for a stop that is on the wrong side
would describe a number that has no meaning.

## What this does not do

The PDP evaluates whether a protective stop is declared and sensible. It does not place one, cancel
one, or notice that one fired. Those are enforcement responsibilities, and an owner reading an
`ALLOW` should not infer that a protective order exists anywhere yet.
