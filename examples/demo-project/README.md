# Demo Project (PCP example target repository)

This directory is a **synthetic target repository** for the Planning Control
Plane. It exists to demonstrate that PCP works on any repository and depends
on no particular product, domain, or business data. All content is generic
placeholder material.

## What is here

- `.planning/` — the planning graph:
  - `project.yaml` — project config, current focus (`P2-A4`), authority roots
  - `roadmap.yaml` — empty; nodes live in `nodes/` (both sources are merged)
  - `nodes/` — one YAML file per planning node (`P1` → `P2` → `P2-A` → `P2-A1..A4`)
- `docs/rollout/` — mock **canonical** documents (normative placeholders)
- `docs/notes/` — mock **current-state/evidence** notes

The demo exercises: frozen decisions at several levels (inherited by child
nodes), a blocking decision (`BD-401` on `P2-A4`), dependencies
(`P2-A4` depends on `P2-A3`; `P2-A3` blocks `P2-A4`), canonical and evidence
links that actually resolve, and a current focus.

## Try it

From this directory (with `pcp` installed from the repository root):

```bash
pcp status          # overview: focus, progress, blockers
pcp context         # session resume capsule for the current focus
pcp context --full  # adds ancestors, related nodes, dependency details
pcp validate        # structural + consistency validation
pcp build           # regenerate .planning/dist (disposable projection)
pcp build --check   # verify dist matches a fresh deterministic build
```

Then open `.planning/dist/index.html` directly (double-click; fully offline).
