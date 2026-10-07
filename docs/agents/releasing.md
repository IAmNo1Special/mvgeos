# Releasing to PyPI

How a `v*` tag becomes an installable `uvx mvgeos`. Uploads authenticate with a
PyPI API token stored as the `PYPI_API_TOKEN` secret on the GitHub `pypi`
environment. It is a long-lived credential: any workflow that declares that
environment can read it, and anyone who obtains it can upload to every project
under the account. That is the trade for not running PyPI's own publisher setup
by hand. See "Moving to a trusted publisher" below for the way back.

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

Two things must exist before the first upload, and only a person can do them.

1. Create or log into the PyPI account that will own the releases, and enable
   two-factor authentication on it. PyPI requires 2FA before it will issue an
   API token.
2. Create an API token on that account, scoped to **upload only**, across all
   projects. One token covers all eight names, because a token cannot be scoped
   to a project that does not exist yet.

Then store it once:

```
gh secret set PYPI_API_TOKEN --repo IAmNo1Special/mvgeos --env pypi
```

An environment secret, not a repository secret, so that only a job declaring
`environment: pypi` can read it. No project has to be created by hand: the
first upload of `mvgeos-core` creates that name on PyPI.

If any name is already claimed by someone else, stop and escalate. Do not
publish under a substitute name.

### Moving to a trusted publisher

PyPI's own answer to a stored token is OIDC trusted publishing: no secret is
kept anywhere, and GitHub mints a 15-minute upload token per run. It needs a
one-time browser step — a pending publisher per project name on
`https://pypi.org/manage/account/publishing/`, with owner `IAmNo1Special`,
repository `mvgeos`, workflow `publish.yml`, environment `pypi`. Then restore
`id-token: write`, set `UV_PUBLISH_TRUSTED_PUBLISHING: always`, drop the two
`UV_PUBLISH_*` credential lines, and delete the secret. PyPI still has no API
for this, which is why it is worth doing deliberately rather than as a
side effect.

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
authenticating as `__token__` with the `PYPI_API_TOKEN` secret. The job fails
immediately if the secret is absent rather than uploading nothing and reporting
success.

`UV_PUBLISH_CHECK_URL=https://pypi.org/simple` makes a re-run after a partial
failure skip whatever already landed. PyPI versions are immutable, so without
this a retry after uploading four of eight packages would fail on the first.

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
