# Mnemox Control — Agent Context

## Project Rules

- Python 3.12+.
- No production behavior without an observed failing test first.
- Contract models reject unknown fields and remain immutable.
- Timestamps are timezone-aware UTC on the wire; financial values use `Decimal`.
- Never add broker credentials, live-order access, or external writes without explicit scope.
- Run pytest, Ruff, mypy, and package build before claiming completion.

## Current Status

- Contracts v0.1 implementation is in progress on `feat/contracts-v0.1`.
- Canonical JSON and SHA-256 helpers are implemented with 4 focused tests passing under the temporary Python 3.11 development runner; final verification must use Python 3.12.
- Next: implement immutable `PolicyBundle` through red-green TDD.

## Recent Changes

- 2026-08-30: Added contracts v0.1 design, implementation plan, task file, package metadata, deterministic canonical serialization, and SHA-256 content hashing.
