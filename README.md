# Planning Control Plane

English | [简体中文](README.zh-CN.md)

**Planning Control Plane (PCP)** is a repository-native tool for maintaining
long-running planning context across branches, decisions, implementation
stages and AI sessions. It turns a planning process that used to live — and
rot — inside long chat transcripts into a persistent **Planning Graph** in
your repository, and projects it as a deterministic, offline static
dashboard.

![Dashboard](docs/screenshots/dashboard-en.png)

## Why PCP?

Long planning conversations fail in a predictable way:

```
long planning conversations → context loss → decision drift → scope drift
```

- **Context loss** — a new session (or a new week) no longer knows the
  parent constraints and the decisions that were already made.
- **Decision drift** — later discussions silently overturn frozen
  decisions, because nobody re-reads message 40 of a 400-message thread.
- **Scope drift** — the discussion quietly grows past what this round was
  supposed to decide.

A regular task tracker does not solve this, because the problem is not
"who is doing what" — it is "where did the context and the boundaries of
the discussion go". PCP manages the structure, progress and context of the
planning process itself, not task assignment.

## The Core Idea

1. **Planning data is source; HTML is a projection.** The Planning Graph
   lives in `.planning/` as plain YAML, committed with your repository.
   `pcp build` renders it into a disposable static site you can delete and
   regenerate at any time.
2. **A tree with inherited memory.** Nodes form a planning tree
   (`PROGRAM → PHASE → STRATEGY → …`). Frozen decisions and scope
   boundaries made at a parent are *inherited and displayed* in every child
   node, so they stay visible instead of being re-litigated.
3. **Current Focus is always recoverable.** One node is the current focus.
   `pcp context` emits a **Context Capsule** — a compact, self-contained
   resume block you paste into a new AI session (or send to a teammate) to
   continue exactly where you left off.
4. **Deterministic and offline.** Same planning source + same PCP version =
   byte-identical output. The generated site references no CDN, no remote
   fonts, no network at all; it works when opened directly via `file://`.

## Features

- **Planning Graph** — nodes with parent / dependency / blocking / related
  / supersedes edges, validated as a graph (cycle detection included)
- **Current Focus** — the single node the next session should work on,
  highlighted in the dashboard and the tree
- **Frozen / Open / Blocking / Deferred Decisions** — categorized,
  inherited down the tree, never silently lost
- **Scope Boundary** — explicit *in scope / out of scope* per node,
  inherited from ancestors, shown on the page and in the capsule
- **Three independent tracks** — discussion, writeback and implementation
  status are stored separately and never derived from each other
- **Context Capsule** — `pcp context <node>` prints a paste-ready resume
  capsule; the node page has a one-click Copy Context button
- **Static dashboard** — deterministic, offline, dark-mode-capable HTML
  with progressive disclosure
- **Bilingual UI** — English and 简体中文, switchable at runtime in the
  browser
- **Repository-native authority boundary** — PCP owns planning only; it
  links to your canonical documents, never replaces them

## Installation

PCP is not yet on PyPI; install from source (Python 3.11+). System Python
installs on many distributions are externally managed (PEP 668), so use a
virtual environment:

```bash
git clone <repository-url> planning-control-plane   # or download and extract the source
cd planning-control-plane
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\activate
pip install -e .
pcp --help
```

Runtime dependencies are just PyYAML and Jinja2.

## Quick Start

In your own repository:

```bash
cd my-project

pcp init          # creates .planning/{project.yaml, roadmap.yaml, nodes/, .gitignore}
```

Create your first planning node — `.planning/nodes/N1.yaml`:

```yaml
id: N1
title: Choose the deployment approach
type: DISCUSSION
status: DISCUSSING

objective: >
  Decide how this service gets deployed, given the constraints we froze
  at the program level.

scope:
  - Deployment tooling
  - Environment topology
out_of_scope:
  - Application refactoring
  - Team staffing

next_action: >
  Compare the two candidate toolchains against the readiness criteria.

discussion_status: IN_PROGRESS
writeback_status: N/A
implementation_status: N/A
last_updated: 2026-08-18
```

Then:

```bash
pcp focus N1      # set the current focus (written to project.yaml)
pcp validate      # structural + consistency checks
pcp build         # generate .planning/dist/
```

Open `.planning/dist/index.html` in a browser — double-clicking works; the
site is fully offline. Continue in the terminal with:

```bash
pcp status        # overview: focus, blockers, progress counts
pcp context       # the resume capsule for the current focus
```

To explore a ready-made example instead, see
[`examples/demo-project`](examples/demo-project) — a synthetic repository
with a seven-node planning tree you can `pcp build` immediately.

## CLI

| Command | What it does |
| --- | --- |
| `pcp init` | Create the `.planning/` skeleton; never overwrites existing files (`--force` only fills in missing files) |
| `pcp validate` | Structural + planning-consistency validation, one issue per line (`ERROR`/`WARNING` + node + rule + reason) |
| `pcp build` | Validate, then deterministically rebuild the HTML output directory |
| `pcp build --check` | Regenerate in a temp dir and compare — drift detection for CI |
| `pcp status` | Terminal overview: project, current focus, decision counts, progress counts |
| `pcp context [node] [--full]` | Print the session resume capsule (default: the current focus) |
| `pcp focus [node]` | Show or switch the current focus (line-oriented edit of `project.yaml`; comments preserved) |

Global option: `-p/--project-root PATH` — target repository root (other
commands search upward for `.planning/`).

Exit codes: `0` success · `1` business failure (validation errors, unknown
node, drift) · `2` usage/load error.

## Planning Model

- **Node types** (controlled enum): `PROGRAM`, `PHASE`, `STRATEGY`,
  `DISCUSSION`, `DECISION`, `INVESTIGATION`, `IMPLEMENTATION`, `CLOSURE`.
- **Node status** (planning lifecycle, not a kanban): `NOT_STARTED`,
  `DISCUSSING`, `INVESTIGATING`, `DECIDED`, `WRITEBACK_PENDING`,
  `WRITEBACK_DONE`, `READY`, `IMPLEMENTING`, `BLOCKED`, `DONE`, `DEFERRED`.
- **Three independent tracks** per node — `discussion_status`,
  `writeback_status`, `implementation_status` ∈ `NOT_STARTED`,
  `IN_PROGRESS`, `DONE`, `N/A`. A pure discussion node can be
  Discussion `DONE` + Writeback `DONE` + Implementation `N/A`.
- **Decisions** come in four lists per node:
  - *Frozen* — settled; children inherit them and must not silently overturn them
  - *Open* — identified, not yet settled
  - *Blocking* — unresolved and preventing closure (`DONE` + blocking → validation ERROR)
  - *Deferred* — deliberately postponed
- **Scope Boundary** — `scope` / `out_of_scope` lists per node; ancestor
  entries are inherited and displayed as guardrails.

## `.planning/` Structure

```
.planning/
├── project.yaml    # project id/name, current_focus, authority roots, ui.locale
├── roadmap.yaml    # optional inline nodes list
├── nodes/          # one YAML file per planning node
└── dist/           # generated site (gitignored, disposable)
```

## Example Node

From `examples/demo-project/.planning/nodes/P2-A4.yaml`:

```yaml
id: P2-A4
title: Rollout Readiness Preflight
type: DISCUSSION
parent: P2-A
status: NOT_STARTED
objective: >
  Run the readiness preflight for the first wave ...
scope:
  - First-wave readiness verification
  - Blocking-issue escalation
out_of_scope:
  - Changing the readiness criteria (frozen at P2-A2)
open_decisions:
  - id: OD-401
    summary: How much readiness evidence is enough to declare the first wave ready?
blocking_decisions:
  - id: BD-401
    summary: Must a blocking gate owner sign off before rollout execution starts?
depends_on: [P2-A3]
canonical_sources:
  - docs/rollout/readiness-criteria.md
evidence_sources:
  - docs/notes/2026-08-15-sequencing-review.md
next_action: >
  Resolve BD-401 with the gate owners, then walk the criteria checklist.
discussion_status: NOT_STARTED
writeback_status: N/A
implementation_status: N/A
last_updated: 2026-08-17
```

## Dashboard & Progressive Disclosure

![Node detail](docs/screenshots/node-en.png)

- The **sidebar** owns the full planning tree — status, focus marker and
  expand/collapse included.
- The **dashboard** answers four questions only: where are we (Current
  Focus), is anything blocked (Needs Attention), what is around the focus
  (Focus Branch), and what can start next (Ready Queue).
- The **node page** is ordered by control-plane priority: sticky header
  (id, status, three tracks, Copy Context) → Next Action → Objective →
  Scope Boundary → decisions (Blocking → Open → Frozen, inherited groups
  collapsed per ancestor) → relations → sources → Resume This Work.
- Details that would bury the essentials start collapsed (inherited frozen
  decisions, deferred decisions, the full capsule) with counts always
  visible.

## Context Recovery

The **Context Capsule** is the bridge between the planning graph and your
next working session:

```bash
pcp context            # compact capsule for the current focus
pcp context P2-A4      # any node
pcp context --full     # adds ancestor summaries, relations, deferred decisions
```

Paste the capsule into a new AI session as the opening context. It carries
the node's objective, inherited frozen decisions, scope boundaries, open
and blocking decisions, sources and track status — everything a fresh
session needs and nothing it should not see. The node page's **Resume This
Work** panel shows the same capsule with a copy button.

## Recommended AI Agent Workflow

```
1. pcp build → open the dashboard, read Current Focus
2. pcp context → paste the capsule into a new agent session
3. Discuss only that branch; record outcomes as decisions in the node YAML
4. Write conclusions that belong in specs back into the canonical docs;
   keep only links in the node
5. Update status / tracks / next_action / last_updated
6. pcp validate → fix ERRORs
7. pcp build (CI: pcp build --check)
8. pcp focus <next-node> → repeat
```

Every artifact of the loop is on disk, so it can be interrupted anywhere
and resumed later.

## Localization

The UI ships in English and 简体中文.

- **Project default** — `ui.locale` in `.planning/project.yaml`:

  ```yaml
  ui:
    locale: zh-CN     # or en (default)
  ```

- **Runtime switch** — the top bar has a `English / 中文` toggle. Switching
  happens instantly in the browser: no rebuild, no refresh, no network. The
  preference is stored in `localStorage` and survives navigation and
  reloads; clearing it falls back to the project default. `project.yaml`
  is never modified.
- **Language never touches data** — node ids, decision ids, stored enum
  values, user-written titles/summaries and the `pcp context` capsule stay
  exactly as written in any locale. Detailed status views show
  `localized label + RAW_ENUM` (e.g. `未开始 NOT_STARTED`), so machine-facing
  values remain searchable.

## Architecture

| Layer | Location | Owner |
| --- | --- | --- |
| PCP engine | `src/planning_control_plane/` (this repository) | standalone pip-installed tool |
| Planning data | `<your-repo>/.planning/{project.yaml, roadmap.yaml, nodes/}` | your repository |
| Generated HTML | `<your-repo>/.planning/dist/` | disposable projection of the data |

Modules: `model.py` (enums + data model) · `loader.py` (tolerant YAML
loading) · `graph.py` (tree/graph operations) · `validator.py` (rules) ·
`context.py` (capsule) · `i18n.py` (UI translations — the single source
embedded into each page) · `generator.py` + `templates/` (deterministic
HTML) · `cli.py`.

## Authority Boundary

PCP is authoritative **only** for planning structure and planning progress.
Normative product, governance, architecture and implementation semantics
remain owned by your project's own documents; PCP links to them
(`canonical_sources` / `evidence_sources`) and never copies or judges them.
Every generated page states this in its footer.

## Current Status

Alpha (`0.1.2`). The engine, CLI, validator, capsule and bilingual UI are
working and covered by an automated test suite (220 tests). PCP is **not
yet published on PyPI** — install from source as shown above. No remote
repository has been set up yet.

## Roadmap

Deliberately **not** in scope: multi-user collaboration, server/cloud sync,
database, GitHub/PR integration, AI plugins, automatic summarization or
decision-making, semantic search, Jira/Notion replacement.

Named extension points reserved for later versions (no interfaces yet):
`pcp prompt`, `pcp close`, `pcp reopen`, Git/GitHub adapters, Claude Code /
Codex / ChatGPT adapters, multi-project workspace.

## Contributing

Issues and pull requests are welcome once the public repository is
announced. For development:

```bash
pip install -e ".[dev]"
python -m pytest
```

## License

[MIT](LICENSE)
