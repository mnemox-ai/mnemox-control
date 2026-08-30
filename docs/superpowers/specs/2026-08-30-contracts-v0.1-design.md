# Mnemox Control Contracts v0.1 — Design

## Goal

Freeze the portable contracts that every future agent, gateway, broker adapter, and verifier will exchange before any broker integration is implemented.

## Scope

This slice defines three immutable value objects:

1. `PolicyBundle`: owner-signed limits that an agent cannot modify.
2. `OrderIntent`: the order an agent proposes, before broker submission.
3. `DecisionReceipt`: the gateway's allow, deny, or escalate decision and its evidence linkage.

It also defines deterministic canonical JSON and SHA-256 identifiers. Ed25519 signing, policy evaluation, credential injection, broker adapters, persistence, and network services are explicitly outside this slice.

## Architecture

The package is pure Python. Pydantic v2 validates wire data and rejects unknown fields. Each model is frozen after construction. Canonical serialization uses UTF-8 JSON with sorted keys, compact separators, no ASCII escaping, and normalized UTC timestamps. Content identifiers are lowercase SHA-256 hex digests of canonical JSON excluding the identifier field itself.

## Contract Decisions

### Shared rules

- Python 3.12 or newer.
- Timestamps must be timezone-aware and are normalized to UTC with a `Z` suffix.
- Identifiers use UUID values supplied by the caller; constructors never read wall-clock time or generate random values.
- Decimal quantities and prices serialize as normalized strings, never binary floats.
- Unknown fields are rejected.
- Models are immutable.
- Canonical JSON output is byte-identical for semantically identical inputs.

### PolicyBundle

Required fields:

- `policy_id: UUID`
- `version: Literal["0.1"]`
- `owner_id: str`
- `account_id: str`
- `broker: str`
- `allowed_symbols: tuple[str, ...]`
- `max_order_notional: Decimal`
- `max_position_notional: Decimal`
- `max_leverage: Decimal`
- `max_daily_loss: Decimal`
- `max_drawdown: Decimal`
- `approval_notional: Decimal`
- `valid_from: datetime`
- `expires_at: datetime`
- `created_at: datetime`
- `content_hash: str | None`

Rules:

- Symbols are trimmed, uppercased, deduplicated, and sorted.
- All monetary/risk limits are non-negative; leverage is greater than or equal to one.
- `approval_notional` cannot exceed `max_order_notional`.
- `valid_from < expires_at` and `created_at <= valid_from`.
- `with_content_hash()` returns a new instance whose hash covers every field except `content_hash`.

### OrderIntent

Required fields:

- `intent_id: UUID`
- `agent_id: str`
- `account_id: str`
- `broker: str`
- `symbol: str`
- `side: Literal["BUY", "SELL"]`
- `order_type: Literal["MARKET", "LIMIT", "STOP"]`
- `quantity: Decimal`
- `limit_price: Decimal | None`
- `stop_price: Decimal | None`
- `reduce_only: bool`
- `strategy_id: str`
- `reason: str`
- `market_data_as_of: datetime`
- `created_at: datetime`

Rules:

- Symbol is trimmed and uppercased.
- Quantity is greater than zero.
- LIMIT requires `limit_price`; STOP requires `stop_price`; MARKET rejects both price fields.
- Price fields, when present, are greater than zero.
- Reason and all identity fields reject blank strings.

### DecisionReceipt

Required fields:

- `receipt_id: UUID`
- `intent_id: UUID`
- `policy_id: UUID`
- `policy_hash: str`
- `decision: Literal["ALLOW", "DENY", "ESCALATE"]`
- `reason_codes: tuple[str, ...]`
- `evaluated_at: datetime`
- `order_intent_hash: str`
- `broker_order_id: str | None`
- `previous_receipt_hash: str | None`
- `content_hash: str | None`

Rules:

- Hash fields are exactly 64 lowercase hexadecimal characters.
- Reason codes are uppercase, deduplicated, and sorted; at least one is required for DENY or ESCALATE.
- DENY and ESCALATE cannot carry a broker order ID.
- `with_content_hash()` returns a new instance whose hash excludes `content_hash`.

## Testing

Tests prove validation boundaries, immutability, timestamp normalization, decimal stability, deterministic canonical bytes, and known SHA-256 fixtures. Every production behavior is introduced by a failing test first.

## Security Boundary

These contracts provide integrity primitives, not authenticity. A SHA-256 content hash does not prove who created a policy. Signature verification and key ownership are required before a future gateway can trust a `PolicyBundle`.

