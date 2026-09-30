# qiven-workspace

The workspace control-plane repository of the Qiven Workspace Dependency
Resolution program (ADR-0052; accepted architecture in qiven-docs
`accepted/2026-09-24/01-qiven-workspace-resolution-architecture.md`).
It carries dependency-control data and bootstrap only — no product
semantics, no canonical cognition, no execution authority.

## First-class consumer (owner direction 2026-09-30, C-059)

The consumer of this repository's surfaces (bootstrap CLI, launcher,
README) is the **local agent** (ZCode + GLM), not a human — the owner's
own direct-usage probability is 0. Primary metric: model consumability
(correct-form recall, no denial round trips, machine-readable output).

**Status: the WR program is DELIVERED (WR-0..WR-8, 2026-09-28).** The
trust policy (qiven-context `governance/workspace-control-trust-policy.json`)
is owner-accepted and admits this chain; every lock node carries a
repository-owned manifest declaration (`declarations/*.json`, mirrored
from each repository's `.qiven/dependencies.json`); the graph resolves
AUTHORITATIVE with zero shadow-only declarations (first full-graph
authoritative resolution 2026-09-28). TCA's repository selector is cut
over to the WorkspaceGeneration under ADR-0058.

## Layout

| Path | Purpose |
| --- | --- |
| `workspace.json` | node universe (schema `qiven-workspace-v1`, qiven-devkit `docs/schemas/`) |
| `workspace.lock.json` | immutable revision snapshot (`qiven-workspace-lock-v1`); generation digest is path-independent |
| `declarations/*.json` | per-node repository-manifest declaration cache (written by lock-update transactions) |
| `bootstrap/qiven-bootstrap.py` | stdlib-only bootstrap: validates the lock subset, identity-checks the locked Devkit BEFORE any import, runs the locked resolver in preflight mode or gates a configure (`gate-configure`) |
| `qiven.cmd` | thin UX launcher (WG-5 = WorkspaceGeneration task 5): no discovery, no pins, no fallbacks |

The sealed WR-0 census served legacy commits through the WR-3..WR-8
migrations and was REMOVED 2026-09-28 (owner direction; history retains
it).

## Use

Preflight / shadow:

    python bootstrap\qiven-bootstrap.py preflight --control <this-repo> --devkit <devkit-checkout>

Authoritative (requires the trust policy):

    python bootstrap\qiven-bootstrap.py gate-configure --repo <repo> --repo-root <path> \
        --preset <preset> --devkit <devkit-checkout> \
        --mode authoritative --trust-policy <qiven-context>/governance/workspace-control-trust-policy.json

Lock movement (the resolver's `lock-update` is the lock's only writer;
the session commits the emitted lock + declaration cache as one
auditable transaction).

## Locator vocabulary (env > local mapping > sibling)

Every path below is a locator, never a selector — whatever resolves is
identity-checked against the lock's `qiven-devkit` node before any use.

- Control checkout: `--control` > env `QIVEN_WORKSPACE_CONTROL` > the
  bootstrap script's own repository root.
- Devkit checkout: `--devkit` > env `QIVEN_DEVKIT_CHECKOUT` >
  untracked `.qiven-workspace.local.json`
  (`{"checkouts": {"qiven-devkit": "<path>"}}`) > the control
  checkout's sibling `qiven-devkit`.

## Authority notes

- Bootstrap and the resolver never mutate this lock; lock movement is an
  explicit governed transaction (architecture doc 01 section 3).
- The ratified routine-advance rule is MECHANIZED in the resolver
  (WR-8): a control commit whose diff from the closest admitted ancestor
  is limited to node advancement auto-admits; manifest/census/schema/
  bootstrap changes require explicit owner admission recorded in the
  trust policy. Lock-entry cadence (ADR-0058 E7.1): a publishing
  session advances the affected nodes in the same window; the TCA index
  build fails closed on divergence.
- The forbidden resolver-pattern gate (qiven-devkit
  `tools/check_resolver_patterns.py`, wired into the devkit publication
  gate) scans all NINE workspace repositories — the eight product
  repositories plus this control repository (third-party singleton
  included; .cmd/.bat launchers covered since 2026-09-28) — for the
  retired architecture's reintroduction.
- Stage-by-stage evidence: qiven-devkit
  `docs/design/workspace-resolution/wr{5,6,7,8}-report.md` +
  `docs/legacy/design/workspace-resolution/wr{0,2,3}-report.md`.
