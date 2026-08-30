# Mnemox Control — Agent Context

## Project Rules

- Python 3.12+.
- No production behavior without an observed failing test first.
- Contract models reject unknown fields and remain immutable.
- Timestamps are timezone-aware UTC on the wire; financial values use `Decimal`.
- Never add broker credentials, live-order access, or external writes without explicit scope.
- Run pytest, Ruff, mypy, and package build before claiming completion.

## Current Status

- Contracts v0.1 implementation is complete on `feat/contracts-v0.1`.
- `PolicyBundle`, `OrderIntent`, and `DecisionReceipt` are immutable strict contracts backed by deterministic canonical JSON and SHA-256 content identifiers.
- Python 3.12.13 verification: 50 tests pass; Ruff passes; strict mypy passes for all 3 source files; sdist and wheel build successfully.
- Built wheel contains only the 3 expected `mnemox_control` modules plus distribution metadata.
- README documents the protocol purpose, example, and security boundary; v0.1 cannot execute trades or authenticate policy ownership.
- No Git remote is configured, so the branch cannot be pushed until an origin is added.

## Recent Changes

- 2026-08-30: Added contracts v0.1 design, implementation plan, task file, package metadata, deterministic canonical serialization, and SHA-256 content hashing.
- 2026-08-30: Added strict frozen contract base and `PolicyBundle` normalization, cross-field validation, UTC handling, and content hashing.
- 2026-08-30: Added `OrderIntent`, `Side`, and `OrderType` contracts with positive quantity/price validation and exact order-type price invariants.
- 2026-08-30: Added `DecisionReceipt` and `Decision` contracts with reason-code normalization, hash-chain support, and broker-order safety invariants.
- 2026-08-30: Added developer README and completed the Python 3.12 pytest/Ruff/mypy/build release gate.
