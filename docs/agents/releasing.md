# Releasing to PyPI

How a `v*` tag becomes an installable `uvx mvgeos`. Uploads authenticate with
OIDC trusted publishing, not a stored credential: GitHub mints a token for the
`publish` job's run, PyPI exchanges it for a short-lived upload credential, and
nothing is kept in the repository. Anyone who obtains that upload credential
still has it until it expires, minutes later.

This depends on a one-time PyPI account step. See "PyPI setup" below — without a
trusted publisher registered per project name, the upload fails closed. That
is deliberate: failing closed is what makes "no stored token" a real property
rather than a stated intention.

## The eight distributions, not seven

The workspace has seven members plus the root distribution. All eight ship to
PyPI, because the root one is the package that owns the `mvgeos` name:

| # | Distribution | Depends on first-party |
| --- | --- | --- |
| 1 | `mvgeos-core` | — |
| 2 | `mvgeos-provider` | `mvgeos-core` |
| 3 | `mvgeos-tome` | — |
| 4 | `mvgeos-runes` | `mvgeos-core` |
| 5 | `mvgeos-agent` | `mvgeos-core`, `mvgeos-provider`, `mvgeos-tome`, `mvgeos-runes` |
| 6 | `mvgeos-cli` | `mvgeos-agent` and the above |
| 7 | `mvgeos` | `mvgeos-cli` — owns the `mvgeos` console script |
| 8 | `mvgeos-gui` | `mvgeos-agent` and the above |

The order is not written down anywhere; it is derived from the dependency
graph at release time:

```
python scripts/check_publish.py --list
```

That way a newly added package cannot be published out of sequence by
forgetting to edit a list.

Any order that puts a dependency before its dependents is valid, and this is
not the only one that has been proposed for the first release. This one puts
`mvgeos` seventh rather than last, because it depends only on `mvgeos-cli` and
`mvgeos-gui` is unrelated to it. PyPI does not check dependencies at upload
time, so ordering is purely about risk: landing the package that owns the
`mvgeos` name early means the headline command starts working before the
largest upload is attempted, rather than after.

## PyPI setup

Uploads authenticate with a **trusted publisher**, registered per project name.
Nothing is stored in this repository. Two things must exist before an upload,
and only a person can do them.

1. Create or log into the PyPI account that will own the releases, and enable
   two-factor authentication on it.
2. Register a GitHub Actions trusted publisher on **each of the eight project
   names**, with exactly these values:

   | Field | Value |
   | --- | --- |
   | Owner | `IAmNo1Special` |
   | Repository | `mvgeos` |
   | Workflow filename | `publish.yml` |
   | Environment | `pypi` |

The workflow filename and the environment are matched character for character
against the job that uploads. Rename either and PyPI rejects the exchange.

### Where the registration goes depends on whether the project exists

This is the step that is easy to get half-right, and getting it half-right
produces a release that uploads most of its packages and then stops.

- **A project that does not exist yet** takes a **pending publisher**, added on
  the account page at `https://pypi.org/manage/account/publishing/`. Pending
  publishers create the project on first use.
- **A project that already exists** takes an ordinary trusted publisher, added
  on that project's own page at
  `https://pypi.org/manage/project/<name>/settings/publishing/`. An account
  page is not where it goes.

All eight names already exist — the first release created them with a stored
token — so all eight belong on their project pages. Measured on the v0.6.17
release: six of the eight uploaded, and `mvgeos` was refused with

```
403 Invalid API Token: OIDC scoped token is not valid for project 'mvgeos'
```

while `mvgeos-gui` was never attempted, because the run stopped at `mvgeos`. A
pending publisher on the account page had been registered for all eight names,
and six of them worked. **Do not assume one registration covers the set**: check
each of the eight project pages individually, and treat a name that 403s as
unregistered rather than as misconfigured.

The refusal names the project, which is the one useful thing in the message. The
publish job surfaces it as such instead of a generic failure — see "A refused
project is not a misconfigured one" below.

If any name is already claimed by someone else, stop and escalate. Do not
publish under a substitute name.

There is no API for this step — it is a browser form — which is why it is a
human prerequisite and not something an agent can unblock.

## What the workflow does

`.github/workflows/publish.yml` runs on any `v*` tag, in three jobs.

**`preflight`** builds every distribution with `uv build --no-sources` and then
runs `scripts/check_publish.py`. `--no-sources` is the important flag:
`[tool.uv.sources]` is a uv-only table that never reaches a wheel, so a build
that relies on the workspace resolving its own siblings is not evidence that
the wheel installs elsewhere. The check then asserts two things:

- every package carries the tag's version, so a release cannot ship a mixed set;
- every first-party `Requires-Dist` in every built wheel carries a version
  constraint, because a bare name resolves against whatever version of the
  sibling happens to be newest on PyPI.

**`publish`** uploads in the derived order, one distribution per step,
authenticating with OIDC: `id-token: write` lets GitHub mint a token for this
run, and `UV_PUBLISH_TRUSTED_PUBLISHING: always` tells `uv` to use trusted
publishing. What enforces "no stored credential" is the absence of any
`UV_PUBLISH_USERNAME` / `UV_PUBLISH_PASSWORD` line in the job plus the deleted
secret — `always` on its own does not. Measured against uv 0.12.10 and 0.12.23:

| | `automatic` | `always` |
| --- | --- | --- |
| OIDC available | uploads via OIDC | uploads via OIDC |
| No credentials of any kind | fails, 0 requests sent | fails, 0 requests sent |
| `UV_PUBLISH_USERNAME`/`PASSWORD` exported | **uploads with them** | **uploads with them** |

So a reintroduced credential line would be used whatever this setting says. The
setting is still worth carrying because it stops `uv` hunting for a credential
by other means, and because it keeps the job honest if someone changes the
mechanism later — but it is not the control.

The job also asserts `ACTIONS_ID_TOKEN_REQUEST_URL` is set, which is what
GitHub puts on the runner for a job granted `id-token: write` and on no other
job. Without that check a dropped `id-token: write` surfaces as uv's generic
"Trusted publishing failed … `_/oidc/audience`", which reads like PyPI refusing
the project rather than a permission mistake.

`UV_PUBLISH_CHECK_URL=https://pypi.org/simple` makes a re-run after a partial
failure skip whatever already landed. PyPI versions are immutable, so without
this a retry after uploading four of eight packages would fail on the first.

### A refused project is not a misconfigured one

PyPI answers "this OIDC token is not valid for project X" with a 403, which
means **X has no trusted publisher matching this run**. It does not mean the
workflow, the workflow filename, or the environment is wrong — if those were
wrong, *every* package in the loop would fail, because one token is minted for
the job and offered to all eight uploads.

So read the scope of the failure as the diagnosis:

| What failed | What it means |
| --- | --- |
| All eight | The workflow filename, owner, repository, or environment is wrong on every registration |
| Some, and it stops partway | Only those project names are unregistered; the rest are fine |

The run stops at the first refusal, so a failure at position seven tells you
nothing about position eight. Check every project page, not just the one named
in the error.

Re-running the same tag is the recovery. `--check-url` skips what already
landed, so a run that uploaded six and refused the seventh resumes at the
seventh. The tag is unchanged and PyPI versions are immutable, so nothing needs
re-releasing.

### When PyPI refuses a project as new

PyPI caps how many *new projects* one account may create in a window, and
answers `429 Too many new projects created` at the cap. The cap is on project
creation, not on uploads to existing projects, so a refusal means "come back
later", not "this distribution is broken".

That is why the first release is the one most likely to hit it: eight names,
eight creations. When it happens, the `publish` job **stops on the first
refusal**. It does not retry, and that is deliberate. PyPI advertises the
policy as `"project.create.user";q=4;w=86400` — four creations counted in the
trailing 24 hours. A retry inside a run cannot outrun that window, so it can
only spend runner minutes; a refused request may itself count against the
window it is waiting for. The run fails red, and the step summary prints when
the quota next has room. Read that time, and re-dispatch the same tag after
it. Re-running is safe and is the normal path, not an exception.

**The quota frees as a trailing window, not one slot per day.** A creation
leaves the window when it turns 24 hours old, so the time a slot frees is the
upload time of the *oldest* project in the window, plus 24 hours. Creations
made seconds apart therefore age out seconds apart, and the whole quota returns
at once. The 0.6.6 first release created its first four names in an 8-second
span, so the full quota of four came back in one go rather than over four days.
Do not plan around a daily drip.

To read the current state and get that time:

```
python scripts/pypi_new_project_window.py
```

The publish job appends the same report to its step summary when it is
refused. It needs no credentials: it reads the public index.

If more names remain than the window holds, the report says so, and it takes
more than one window. That is the only case where asking PyPI for a lift is
worth the wait: open a request at `https://github.com/pypi/support/issues/new`,
choosing "Limit Request", and note that this is a coordinated first release of
eight distributions in dependency order, how many already landed, and that the
account is not being recreated. Expect it to take days to be answered.

**`verify`** checks out nothing at all and runs `uvx mvgeos --help`. Because
there is no clone and no `uv sync`, uvx resolves the command from PyPI exactly
as a stranger's machine would. That job is the acceptance test; `pip download`
is not.

**`verify-install`** runs `scripts/verify_install.py`, which is the half
`verify` structurally cannot reach. `--help` returns before a Realm is
contacted, so a release whose credential never loads, whose Realm Rune is
missing, or whose Tome never reaches disk is green and still unusable. The
script builds a scratch `HOME` that starts empty apart from the credential,
installs `openrouter-realm` and `coding_mvge` into it, runs one real task, and
fails unless the artifact is byte-correct and a session Tome naming the model
lands under `.agents/sessions/`. It reports cold-to-first-token on the way.

Unlike `verify`, this job checks the repository out — only to get the script.
Every mvgeos the run touches still comes from PyPI through uvx, so the thing
under test is the published distribution and never the workspace.

The script is stdlib-only so that the thing standing between a release and this
check cannot itself fail to install, and it needs the repository secret
`OPENROUTER_API_KEY`. If that secret is absent the job **fails on purpose**
rather than skipping: a skipped gate is indistinguishable from a passing one
once a run is green, which is how the check would come to protect nothing. A
repository owner adds it under Settings > Secrets and actions > Actions.

Where `bwrap` is available — the job installs it, and most developer machines
have it — the script re-runs itself inside a sandbox and says so on its first
line. That is a real narrowing of what the run can see: a mount, process, and
UTS namespace in which the checkout and the operator's own `HOME` do not exist,
which is the difference between "a stranger's HOME" and "a stranger's machine".
The network namespace is deliberately *not* unshared, because resolving mvgeos
from PyPI and reaching a Realm are the two things under test. The script checks
the isolation from the inside and fails if a host path is still reachable, so a
sandbox that leaks is a red gate rather than a quiet one. Pass `--no-sandbox`
to run without it.

The model defaults to `openai/gpt-4o-mini` and `--max-tokens` is capped, so a
run costs a fraction of a cent and survives a key whose remaining credit cannot
cover the engine's 4096 default. Override both when a specific failure needs a
different target:

```bash
OPENROUTER_API_KEY=sk-or-... python scripts/verify_install.py \
  --version 0.6.14 --model anthropic/claude-sonnet-4 --max-tokens 8000
```

## The normal path

The `bump` job in `ci.yml` creates and pushes the tag after a green `main`, then
dispatches `Release` and `Publish` itself. Nothing has to be done by hand after a
merge to `main`.

The dispatch is explicit because the tag push alone is not a trigger. That push
uses `GITHUB_TOKEN`, and GitHub's loop guard stops a `GITHUB_TOKEN` push from
starting any workflow, so the `v*` tag trigger in `publish.yml` never fires from
the `bump` job. The `bump` job calls both workflows instead:

```
gh workflow run Release --ref main -f version=v0.6.5 -f dry_run=false
gh workflow run Publish --ref v0.6.5 -f tag=v0.6.5 -f dry_run=false
```

`Publish` is dispatched against the tag rather than `main` on purpose. A tag push
gives the workflow `GITHUB_REF=refs/tags/v0.6.5`, so `preflight` builds exactly
the tagged commit. Dispatching against `main` would build whatever `main` holds
when the runner starts, which can be a commit that landed after the tag, and
those wheels would be published and permanently labelled `v0.6.5`.

## When a publish run needs redoing by hand

Re-run the same tag. `UV_PUBLISH_CHECK_URL` skips every package that already
landed, so the run resumes rather than restarting:

```
gh workflow run publish.yml --ref v0.6.5 -f tag=v0.6.5 -f dry_run=true
gh workflow run publish.yml --ref v0.6.5 -f tag=v0.6.5 -f dry_run=false
```

Dry run first. It builds and validates everything and uploads nothing.

The most common reason for a red `Publish` run is PyPI's cap on new project
creations, not a packaging fault. See "When PyPI refuses a project as new" above.

A hand-pushed tag also fires `publish.yml` through its own `v*` tag trigger,
because a push made with a person's token is not covered by the loop guard. That
path builds the tag correctly too, but it is not needed and it skips the gates
`bump` waits on.

## After a release

The `mvgeos-gui` upload is last because it is the largest and the least likely
to be the reason someone ran `uvx mvgeos`. If one upload in the middle fails,
the run stops there. Re-run the same tag: `--check-url` skips the packages
that already landed and continues with the rest.

## When the bump job cannot land

The `bump` job commits, rebases onto whatever `main` is at that moment, tags,
and pushes. It holds a concurrency group, so a second push to `main` queues
behind a bump already in flight rather than racing it.

If a hand push lands on `main` in the middle of a bump and the rebase
conflicts, the job aborts the rebase and exits green with a warning instead of
red. Nothing is tagged and nothing is released, which is deliberate: the next
push to `main` re-runs the whole bump against content that already contains the
conflict resolution. Read the warning on the run rather than assuming a release
happened.
