# Lock-blocking git hooks (ADR-0062 c4)

These tracked git hooks mechanically enforce the accepted ordering for
workspace.lock.json: the lock moves only after accepted publication.
Any transaction mutating `workspace.lock.json` is denied while ANY node
in the NEW lock names a commit that is not PUBLISHED - not reachable
from that node repository's `main` on its remote. Transactions that do
not touch the lock pass unchanged.

## Mechanism

- `pre-commit` — the staged (index) version of the lock is the NEW
  lock; every node's `commit` must be an ancestor of (or equal to)
  `refs/remotes/origin/main` in the node's checkout.
- `pre-merge-commit` — the index holds the merge result; when the
  merge changes the lock versus HEAD, the same check runs.
- `pre-push` — for every pushed range, every commit that mutates the
  lock (blob change versus its first parent; deletion denied) must
  name only published nodes per the CURRENT remote-tracking refs.
- Node checkout resolution mirrors the bootstrap locator law:
  explicit `.qiven-workspace.local.json` `checkouts` entry wins, else
  the control checkout's sibling directory named after the node. An
  undeclared node, a missing sibling checkout or an unreadable
  remote-tracking ref fails CLOSED with a named error.
- Denials name the node, the unpublished SHA and the remediation:
  publish the referenced repository head first, fetch, then
  re-advance the lock.

## Freshness assumption (stated honestly)

Verification uses each sibling checkout's remote-tracking
`refs/remotes/origin/main` — the state of the last fetch, not a live
query (the hooks never touch the network). The operator flow MUST
fetch in each node checkout before lock movement, otherwise a stale
tracking ref can make an already-superseded remote state look
current. Fail-closed direction: a missing tracking ref denies; a
stale-but-present one can only over- or under-report publication as
of the last fetch.

## Activation (machine-local, hooks are tracked files)

    git config core.hooksPath tools/hooks

Python resolution: an explicit `QIVEN_HOOK_PYTHON` locator wins;
otherwise the repository `.venv` if present; otherwise `python` from
PATH (the guard is standard library only). On POSIX checkouts also
make the wrappers executable (`git update-index --chmod=+x
tools/hooks/pre-commit tools/hooks/pre-merge-commit
tools/hooks/pre-push`); Git for Windows executes them as-is.

## Residuals (stated honestly)

- `--no-verify` bypasses any git hook: mechanical blocking covers
  ordinary paths, not adversarial ones.
- Remote-tracking freshness (above): fetch before lock movement.
- A node commit that is an ANCESTOR of remote main counts as
  published (it was published earlier); the lock deliberately may sit
  behind a node's remote main.
- Deletion pushes (zero local sha) add no commits and are not
  blocked; deleting the lock file itself in a pushed commit is denied.

## Tests

`tools/hooks/lock_hooks_test.py` builds a local sandbox (a node
repository with a local bare remote + this control repository) and
proves: lock advance to a remote-main-published SHA passes; advance
to a local-only unpushed SHA is denied; non-lock commits are
unaffected; a pushed lock-mutating commit referencing an unpublished
node commit is denied at push time and passes once the node head is
published.
