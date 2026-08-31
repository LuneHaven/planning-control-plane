# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com); versioning
follows SemVer (pre-1.0: breaking changes may land in a minor bump).

## [0.1.3] - 2026-09-01

First release published to PyPI.

### Added

- Planning Graph: planning nodes as YAML under `.planning/`, with
  parent / dependency / blocking / related / supersedes edges and
  graph-level validation (cycle detection included)
- CLI: `pcp init` / `validate` / `build` / `build --check` / `status` /
  `context` / `focus` / `ideas` / `graduate`
- Deterministic, fully offline static dashboard with progressive disclosure
  and a bilingual UI (English / 简体中文)
- Context Capsule: paste-ready session recovery via `pcp context`
- Idea layer: `.planning/ideas/` with a graduation workflow (`pcp graduate`)
- Release automation: tag-triggered GitHub Actions workflow with
  PyPI Trusted Publishing

### Notes

- Versions up to 0.1.2 were never published to PyPI; that history lives in
  git (tag `v0.1.2`, 2026-08-18).

## [0.1.2] - 2026-08-18

Usable MVP validated through real-project self-use: engine, CLI, validator,
capsule and bilingual UI (409 automated tests). Distributed as source only.
