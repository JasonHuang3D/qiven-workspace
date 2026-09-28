# qiven-workspace

The workspace control-plane repository of the Qiven Workspace Dependency
Resolution program (ADR-0052; accepted architecture in qiven-docs
`accepted/2026-09-24/01-qiven-workspace-resolution-architecture.md`).
It carries dependency-control data and bootstrap only — no product
semantics, no canonical cognition, no execution authority.

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
| `bootstrap/qiven-bootstrap.py` | stdlib-only bootstrap: validates the lock subset, identity-checks the locked Devkit BEFORE any import, runs only the locked resolver in preflight mode |
| `qiven.cmd` | thin UX launcher (WG-5): no discovery, no pins, no fallbacks |

The sealed WR-0 census (`census/wr0-declarations.json`) served legacy
commits without repository manifests through the WR-3..WR-8 migrations
and was REMOVED at owner direction on 2026-09-28 once the last census
binding (qiven-docs) retired — git history retains it.

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

Optional per-machine checkout mapping lives in an untracked
`.qiven-workspace.local.json` (`{"checkouts": {"qiven-devkit": "<path>"}}`);
a path is a locator, never a selector.

## Authority notes

- Bootstrap and the resolver never mutate this lock; lock movement is an
  explicit governed transaction (architecture doc 01 section 3).
- The ratified routine-advance rule is MECHANIZED in the resolver
  (WR-8): a control commit whose diff from the closest admitted ancestor
  is limited to node advancement auto-admits; manifest/census/schema/
  bootstrap changes require explicit owner admission recorded in the
  trust policy.
- Lock-entry cadence (ADR-0058 E7.1): a publishing session advances the
  affected nodes in the same window; the TCA index build fails closed
  on divergence (the selector gate).
- The forbidden resolver-pattern gate (qiven-devkit
  `tools/check_resolver_patterns.py`, wired into the devkit publication
  gate) scans all NINE workspace repositories — the eight product
  repositories plus the control repository itself, including the
  third-party singleton (extended 2026-09-28 to cover .cmd/.bat
  launchers as well) — for the retired architecture's reintroduction.
- Stage-by-stage evidence: qiven-devkit
  `docs/design/workspace-resolution/wr{0,2,3,5,6,7,8}-report.md`.
