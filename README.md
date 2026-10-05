# qiven-workspace

The workspace's control-plane repository: its **identity ledger and
graph validator** (semantic boundary below). It carries
dependency-control data and bootstrap only — no product semantics, no
canonical cognition. It does not own product behavior or execution
authority, but it is not inert: it enforces dependency admission at
operator import (devkit identity check with the shadow/authoritative
mode boundary) and at native configure (validated resolution adapter
and matching provider revisions).

Mechanism origin, as a pointer rather than a boundary: delivered by
the Qiven Workspace Dependency Resolution program (ADR-0052; accepted
architecture in qiven-docs
`accepted/2026-09-24/01-qiven-workspace-resolution-architecture.md`).

## Semantic boundary — what the lock enforces and what it does not

Adopted definition — accepted qiven-docs PR15 audit §9.4 (2026-10-04),
adopted 2026-10-06:

> qiven-workspace is the workspace's **identity ledger and graph
> validator**: `workspace.lock.json` records one admitted (commit, tree)
> per repository, `declarations/` binds each node to its
> repository-owned manifest, and the WorkspaceGeneration digest makes
> every graph state content-addressable and comparable. Standard WR-6
> launchers check devkit commit/tree identity before operator import
> and invoke resolver preflight, which validates all locked declarations
> and their graph, including context/docs/math. The default shadow mode
> labels dirty devkit changes and permits execution; authoritative mode
> rejects them. Native configure separately requires a validated
> resolution adapter and matching provider revisions. Thus the README's
> "no execution authority" wording needs to distinguish owning product
> behavior from enforcing dependency admission at import and configure.
> Runtime CI materializes five dependency nodes (excluding context),
> but that is not the graph validator's reading boundary. TCA consumes
> context's locked identity and stamps WorkspaceGeneration as provenance,
> not as content input; the activation surface reports the roster as
> informational. The c4 lock-guard hooks require node commits to be
> reachable from local origin/main tracking refs before lock publication;
> that check does not prove remote freshness or node-side review pedigree.
> Routine advances auto-admit by diff-shape. The evidence records both
> real protections and recurring publication costs, without establishing
> commensurable net-value balance.

In operational terms, the lock enforces:

- **Devkit identity at import** — launchers check the locked devkit
  (commit, tree) before any operator import; default shadow mode
  labels dirty devkit changes and permits execution, authoritative
  mode rejects them.
- **Full-graph validation** — resolver preflight validates every
  locked declaration and every graph edge, including context/docs/math.
- **Configure admission** — native configure requires a validated
  resolution adapter and matching provider revisions.
- **TCA closure selection** — TCA consumes context's locked identity
  and stamps WorkspaceGeneration as provenance, not as content input.

The lock does not enforce the invoking repository's own checkout
state: the node-vs-checkout comparison for the invoking repo is a
known blind spot — the activation-surface carrier is the closing
surface. (Publication-side residuals — freshness bounded by the last
fetch, unverified tracking-ref pedigree, `--no-verify` bypass — are
stated in the hooks section below.)

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
last fetch; tracking-ref pedigree is unverified — are stated in
`tools/hooks/README.md`, along with the
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
