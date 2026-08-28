---
name: pcp
description: Use when working in a repository that contains a .planning/ directory (managed by the Planning Control Plane CLI) - starting or resuming work, reading planning context, capturing or graduating an idea, validating planning data with pcp validate before wrapping up, or naming planning documents.
---

# Planning Control Plane (`pcp`)

`pcp` is a repository-native planning tool. The planning data lives in
`.planning/` as YAML files and **the files are the source**: `pcp` reads them,
and only three commands write into that directory. The HTML under
`.planning/dist/` is a generated projection — never edit it by hand.

**This file is the manual for the tool. The rules for a given repository live
in that repository's own AGENTS.md** (naming conventions, registration
conventions, anything project-specific). Read AGENTS.md and follow it; if it
disagrees with this file about repository conventions, AGENTS.md wins.

## Session workflow

1. Starting or resuming work → `pcp context` (the resume capsule for the
   current focus). Add a node id for a specific node, `--full` for ancestors,
   related nodes and dependency detail.
2. Orienting → `pcp status` (planning graph) and `pcp ideas` (idea layer).
3. Capturing a thought that is not a decision yet → write an idea file
   (see below), do not grow the planning graph for it.
4. Wrapping up → `pcp validate`, clear every ERROR. WARNINGs are advisory.

## Commands

| Command | What it does |
| --- | --- |
| `pcp init` | Create the `.planning/` skeleton. Never overwrites; `--force` only fills in missing files. |
| `pcp agents` | Print the AGENTS.md snippet for this tool. Read-only — append it yourself: `pcp agents >> AGENTS.md`. |
| `pcp validate` | Structural + consistency checks, one issue per line (`ERROR` / `WARNING` + id + rule + reason). |
| `pcp status` | Project, current focus, decision counts, progress counts. |
| `pcp context [node] [--full]` | The paste-ready session resume capsule. |
| `pcp focus [node]` | Show or switch the current focus. **Writes** `project.yaml` (line-oriented; comments survive). |
| `pcp ideas [--status S] [--for NODE [--subtree]]` | List the idea layer grouped by status. The last line prints the next free idea id. |
| `pcp graduate IDEA --to NODE [--note TEXT]` | **Writes** two files: promotes the idea and copies its ref-carrying justification into the node's `evidence_sources`. |
| `pcp build [--check]` | Regenerate the HTML projection; `--check` compares instead of writing (CI drift detection). |

Global option `-p/--project-root PATH` must come **before** the subcommand.

Exit codes: `0` success · `1` business failure (validation errors, unknown
node, drift) · `2` usage or load error.

## Write semantics

Only `pcp init`, `pcp focus` and `pcp graduate` write into `.planning/`
(`pcp build` writes the projection directory only). Both `focus` and
`graduate` are line-oriented edits that preserve comments and layout, and
`graduate` verifies after writing and restores both files if the check fails.
Everything else is read-only.

## Ideas

Ideas are uncommitted thinking; planning nodes are post-decision. Capture an
idea as a file — there is no create command:

```yaml
# .planning/ideas/IDEA-0001.yaml
id: IDEA-0001
title: One line — what the thought is
status: OPEN               # OPEN | PARKED | PROMOTED | DISCARDED
detail: |
  Free text.
relates_to: []             # planning node ids this thought touches
benchmark_sources: []      # - ref: docs/note.md   (repository-relative)
methodology_sources: []    # - note: free text
created: 2026-01-01
last_updated: 2026-01-01
```

The next free id is the last line of `pcp ideas`. A broken idea file never
blocks planning: it becomes a validation issue and is skipped.

When an idea becomes a decision, graduate it into an existing node —
`pcp graduate` never creates the node for you.
