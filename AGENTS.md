<!-- pcp:agents begin v1 -->
## Planning Control Plane (PCP)

This repository is managed by PCP. `.planning/` holds the planning data and is
the single source of truth; `.planning/dist/` is a generated projection — never
edit it by hand, run `pcp build` to regenerate it.

**Session workflow**

- Starting or resuming work: run `pcp context` first (pass a node id for a
  specific node, `--full` for ancestors and dependency detail).
- Overview: `pcp status` for the planning graph, `pcp ideas` for the idea layer.
- Before wrapping up: run `pcp validate` and clear every ERROR. WARNINGs are
  advisory and do not block.

**Capturing an idea**

Ideas are files, not a CLI write path: create `.planning/ideas/IDEA-<NNNN>.yaml`
yourself. The next free id is printed on the last line of `pcp ideas`. Minimal
skeleton:

```yaml
id: IDEA-0001
title: One line — what the thought is
status: OPEN               # OPEN | PARKED | PROMOTED | DISCARDED
detail: |
  Free text. Why this might matter, what is still open.
relates_to: []             # planning node ids this thought touches
benchmark_sources: []      # - ref: docs/some-note.md   (repo-relative)
methodology_sources: []    # - note: free text, for anything outside the repo
created: 2026-01-01
last_updated: 2026-01-01
```

Fill `relates_to` with the node ids this thought touches: an idea with no entry
there hangs off no node, and `pcp ideas --for <node>` will never surface it.

**Graduating an idea**

`pcp graduate <idea-id> --to <node-id> [--note TEXT]` sets `status: PROMOTED`
plus `outcome` on the idea and copies its ref-carrying justification entries
into the node's `evidence_sources`. The target node must already exist under
`.planning/nodes/` — PCP never authors planning semantics for you.

**Naming planning documents**

One-shot artifacts (plans, research notes, session records): `YYYY-MM-DD-<slug>.md`.
Long-lived specs keep a stable slug instead (`<topic>-spec.md`) — a spec is
revised for months, so a birth date in its name misleads the reader.

**Registration convention**

When a spec or plan lands, put its repository-relative path into the matching
idea's `benchmark_sources` / `methodology_sources` as a `ref`. `pcp ideas` then
shows which thoughts already have a spec or a plan behind them.
<!-- pcp:agents end -->
