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
- Evaluation Kernel v0.2 Task 3 is complete: trusted account snapshots bind a positive state version, signed positions, every non-terminal/UNKNOWN order, P&L period, drawdown, halt state, and deterministic content hash.
- Account contracts sort evidence by stable keys and reject duplicate position symbols/order IDs, invalid exposure values, invalid P&L windows, bad hashes, unknown fields, and mutation; 82 tests pass.
- Evaluation Kernel v0.2 Task 4 is complete: `PolicyBundle` now requires protocol 0.2, structural revision linkage, positive risk/freshness limits, price/order/reversal controls, UTC risk-day configuration, and normalized non-overlapping weekly windows.
- Deterministic evaluator test factories now provide sealed default policy/account/market/catalog inputs and pending-order/intent helpers; 103 tests pass, Ruff and strict mypy pass.
- Evaluation Kernel v0.2 Task 5 is complete: the exact 36-code protocol order, rule outcomes, position effects, structured `RuleResult`, and proof-carrying `EvaluationResult` are implemented.
- Result validation prevents missing/duplicate rules, false PASS through SKIP, non-prior/non-DENY dependencies, decision-precedence mismatch, unjustified undefined metrics, bad hashes, and mutable evidence; 115 tests pass.

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
- 2026-08-30: Added trusted account, signed position, pending-order exposure, order-status, and halt-state contracts with conservative UNKNOWN-order representation.
- 2026-08-30: Migrated `PolicyBundle` from v0.1 to v0.2 and added revision lineage, freshness, execution-shape, risk-day, weekly-window controls, and deterministic shared test factories.
- 2026-08-30: Added the ordered 36-rule evaluation evidence contract with canonical normalization, dependency validation, worst-outcome decision enforcement, and deterministic content sealing.
