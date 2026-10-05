# qiven-workspace

The workspace control-plane repository of the Qiven Workspace Dependency
Resolution program (ADR-0052; accepted architecture in qiven-docs
`accepted/2026-09-24/01-qiven-workspace-resolution-architecture.md`).
It carries dependency-control data and bootstrap only — no product
semantics, no canonical cognition, no execution authority.

Scope/lifecycle note: this birth-certificate self-description names
the program that first delivered the mechanism. The workspace's
standing semantics (declared working set + identity/resolution
authority + shared enforcement substrate; first-class consumers
beyond builds, incl. the local agent chain) are under deliberation in
qiven-docs PR #13 - until that adjudication lands, this README's
program framing is historical-origin wording, not a semantic
boundary.

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
| `bootstrap/qiven-bootstrap.py` | stdlib-only bootstrap: validates the lock subset, identity-checks the locked Devkit BEFORE any import, runs the locked resolver in preflight mode or gates a configure (`gate-configure`); every typed failure — preflight AND the gate-configure return-1 sites — emits the `qiven-workspace-bootstrap-error-v1` envelope with an additive Common Record (`rule_id` + `next_action`; ADR-0060 D3) |
| `qiven.cmd` | thin UX launcher (WG-5): no discovery, no pins, no fallbacks; the only launcher-owned surface is a typed interpreter-availability probe (four-element `[FAIL]` carrier, exit 2) and verbatim argv/exit-code forwarding to the bootstrap |

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
auditable transaction). Exact invocation shape (validation-only default;
`--apply` writes the transaction into this control tree):

    python <devkit>/tools/workspace_resolver.py lock-update \
        --control <this-repo> --move NODE=<checkout> [--move NODE2=<checkout2>]
    # authoritative movement adds:
    #   --mode authoritative --trust-policy <qiven-context>/governance/workspace-control-trust-policy.json --apply

`--move` targets must be clean at their exact HEAD and are
identity-checked; the receipt lands under
`<workspace-root>/.generated-temp/workspace-resolver/<stamp>-lock-update/receipt.json`.
The receipt's `next_action` names the remaining step (`--apply` mode:
commit this control repository now).

## Lock-movement blocking hooks (ADR-0062 c4)

`tools/hooks/` carries tracked git hooks (`pre-commit`,
`pre-merge-commit`, `pre-push`) that mechanically block any commit,
merge or push mutating `workspace.lock.json` while a node in the NEW
lock names a commit not reachable from that node repository's
remote-tracking `refs/remotes/origin/main` — fail-closed against
undeclared nodes and missing sibling checkouts (an explicit
`.qiven-workspace.local.json` entry deterministically wins over the
sibling directory; there is no ambiguity to detect).
Activation is machine-local: `git config core.hooksPath tools/hooks`.
Verification uses remote-tracking refs (the last fetch, never the
network): fetch in each node checkout before lock movement.
The published state these hooks verify against is established upstream
by the qiven-context c4 publication chain (branch -> clean-context
review at committed head -> exact-head gate -> pre-publication receipt
-> merge/push, enforced by tracked hooks in qiven-context); the
pre-publication receipt contract is
`qiven-context schema/pre-publication-receipt.schema.json`, owned by
the qiven-context repository.
Residuals — `--no-verify` bypasses hooks; freshness is bounded by the
last fetch — are stated in `tools/hooks/README.md`, along with the
sandbox test (`tools/hooks/lock_hooks_test.py`) that proves the
blocking matrix end to end.

## Discovery surface (B6)

Canonical usage for every Qiven mechanism — operator subcommands
(`surface` lists a repo's gates/tasks O(1); `records` reads back operator
records), the workspace mechanisms above, the devkit tool surfaces
(schema-check `--list`, deploy bundle) — is
qiven-devkit `docs/conventions/operator-usage.md`, reachable from each product
repository's AGENTS.md pointer chain. This README stays the authority for
locator vocabulary, the trust policy and the WR history.

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
