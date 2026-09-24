# qiven-workspace

The workspace control-plane repository of the Qiven Workspace Dependency
Resolution program (ADR-0052; accepted architecture in qiven-docs
`accepted/2026-09-24/01-qiven-workspace-resolution-architecture.md`).
It carries dependency-control data and bootstrap only — no product
semantics, no canonical cognition, no execution authority.

**Status: WR-1 shadow proposal.** WR-0 sealed outputs were accepted by
the owner on 2026-09-25 and WR-1 (this repository) was authorized. The
repository becomes an authority only after the independently held
control-repository trust policy is owner-accepted and admits an exact
revision (qiven-context `governance/workspace-control-trust-policy.json`);
until then every receipt from this tree is labeled shadow-only and can
neither authorize a class cutover nor serve WR-7.

## Layout

| Path | Purpose |
| --- | --- |
| `workspace.json` | node universe (schema `qiven-workspace-v1`, qiven-devkit `docs/schemas/`) |
| `workspace.lock.json` | immutable revision snapshot (`qiven-workspace-lock-v1`); generation digest is path-independent |
| `census/wr0-declarations.json` | sealed WR-0 census declarations for legacy commits without `.qiven/dependencies.json`, bound to exact commit/tree, shadow-only until repository-owned manifests land (WR-3..WR-6) |
| `bootstrap/qiven-bootstrap.py` | stdlib-only bootstrap: validates the lock subset, identity-checks the locked Devkit BEFORE any import, runs only the locked resolver in preflight mode |
| `qiven.cmd` | thin UX launcher (WG-5): no discovery, no pins, no fallbacks |

## Use (shadow mode)

    qiven.cmd --devkit <path-to-locked-devkit-checkout>

or explicitly:

    python bootstrap\qiven-bootstrap.py --control <this-repo> --devkit <devkit-checkout>

Optional per-machine checkout mapping lives in an untracked
`.qiven-workspace.local.json` (`{"checkouts": {"qiven-devkit": "<path>"}}`);
a path is a locator, never a selector.

## Authority notes

- Bootstrap and the resolver never mutate this lock; lock movement is an
  explicit governed transaction (architecture doc 01 section 3).
- The legacy devkit pin split (qiven-context executes `d1d2a3a4` via
  shim+pin; C++ repositories execute managed template snapshots; devkit
  main has moved on) is recorded by the census and reported by the
  resolver as a typed baseline conflict — a WR-6 reconciliation target,
  never silently resolved.
