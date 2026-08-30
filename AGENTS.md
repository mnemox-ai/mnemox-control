# Mnemox Control — Agent Context

## Project Rules

- Python 3.12+.
- No production behavior without an observed failing test first.
- Contract models reject unknown fields and remain immutable.
- Timestamps are timezone-aware UTC on the wire; financial values use `Decimal`.
- Never add broker credentials, live-order access, or external writes without explicit scope.
- Run pytest, Ruff, mypy, and package build before claiming completion.

## Current Status

- Contracts v0.1 implementation is complete on `feat/contracts-v0.1` at commit `86cc71c`.
- `PolicyBundle`, `OrderIntent`, and `DecisionReceipt` are immutable strict contracts backed by deterministic canonical JSON and SHA-256 content identifiers.
- Python 3.12.13 verification: 50 tests pass; Ruff passes; strict mypy passes for all 3 source files; sdist and wheel build successfully.
- Built wheel contains only the 3 expected `mnemox_control` modules plus distribution metadata.
- README documents the protocol purpose, example, and security boundary; v0.1 cannot execute trades or authenticate policy ownership.
- No Git remote is configured, so the branch cannot be pushed until an origin is added.
- Evaluation Kernel v0.2 design was approved by Sean on `feat/evaluation-kernel-v0.2` at commit `b956177`.
- v0.2 separates the deterministic PDP from the future non-bypassable PEP, binds evaluations to full account/market/instrument state, and uses worst-case pending exposure without cross-order netting.
- Approved product boundary: Apache protocol/conformance materials, AGPL plus commercial dual-license engine, and proprietary managed trust/enforcement services. No license files change before the implementation plan is approved.
- The reviewed implementation plan is committed at `c8e2a39` and splits v0.2 into 10 strict TDD tasks covering distribution, contracts, policy migration, evidence, calculations, preflight, risk rules, conformance/property tests, and the Python 3.12 release gate.
- Evaluation Kernel v0.2 Task 1 is complete: package version is 0.2.0, engine code is `AGPL-3.0-only`, protocol/conformance assets are Apache-2.0, and the commercial-license path is explicitly separate.
- SPDX license texts were copied without modification (ignoring only final newline); Hypothesis 6.167.0 is installed for the planned property tests; 52 tests pass.
- Evaluation Kernel v0.2 Task 2 is complete: immutable instrument catalogs and market snapshots enforce recognized enum vocabularies, broker/identity uniqueness, positive quote/instrument constraints, UTC timestamps, and canonical sealing.
- The shared timestamp validator now rejects naive timestamps even when supplied as strings; 70 tests pass, Ruff passes, and strict mypy passes across 4 source files.

## Recent Changes

- 2026-08-30: Added contracts v0.1 design, implementation plan, task file, package metadata, deterministic canonical serialization, and SHA-256 content hashing.
- 2026-08-30: Added strict frozen contract base and `PolicyBundle` normalization, cross-field validation, UTC handling, and content hashing.
- 2026-08-30: Added `OrderIntent`, `Side`, and `OrderType` contracts with positive quantity/price validation and exact order-type price invariants.
- 2026-08-30: Added `DecisionReceipt` and `Decision` contracts with reason-code normalization, hash-chain support, and broker-order safety invariants.
- 2026-08-30: Added developer README and completed the Python 3.12 pytest/Ruff/mypy/build release gate.
- 2026-08-30: Designed Evaluation Kernel v0.2 around proof-carrying evaluations, explicit trust roles, temporal/version binding, conservative multi-symbol exposure, rule evidence, and future authorization/reconciliation seams.
- 2026-08-30: Added the approved v0.2 implementation plan and replaced `tasks.txt` with ten self-contained auto-Codex tasks.
- 2026-08-30: Established the v0.2 engine/protocol license boundary, added exact SPDX license texts and commercial licensing notice, bumped the package to 0.2.0, and added Hypothesis to dev dependencies.
- 2026-08-30: Added sealed instrument/catalog and market/quote contracts, including deterministic hash support and known-but-unsupported instrument representation.
