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

PyPI caps how many *new projects* one account may create in a rolling 24-hour
window, and answers `429 Too many new projects created` at the cap. The cap is
on project creation, not on uploads to existing projects, so a refusal means
"come back later", not "this distribution is broken".

That is why the first release is the one most likely to hit it: eight names,
eight creations. When it happens, the `publish` job retries the refused
distribution with a backoff, and the run goes red only if the window has not
freed a slot in time. Two things to know:

- A retry inside the job only covers a short window. A full 24 hours still ends
  in a red run, and the fix is to re-run the same tag later. Re-running is safe
  and is the normal path, not an exception.
- PyPI frees the quota one slot at a time as the window rolls, so a re-run may
  publish some of the remainder and be refused again on the next one. Expect to
  re-run more than once for a first release, and expect the number of runs to
  fall as fewer names remain unpublished.

To ask PyPI for a one-time lift, open a request at
`https://github.com/pypi/support/issues/new`, choosing "Limit Request". Note in
it that this is a coordinated first release of eight distributions in dependency
order, that four already landed, and that the account is not being recreated.

**`verify`** checks out nothing at all and runs `uvx mvgeos --help`. Because
there is no clone and no `uv sync`, uvx resolves the command from PyPI exactly
as a stranger's machine would. That job is the acceptance test; `pip download`
is not.

## Running it by hand

Dry run first. It builds and validates everything and uploads nothing:

```
gh workflow run publish.yml -f tag=v0.6.5 -f dry_run=true
```

Then the real thing, on the tag:

```
git tag v0.6.5 && git push origin v0.6.5
```

The `bump` job in `ci.yml` already creates and pushes the tag after a green
main, so in the normal path there is nothing to do — the release commit is the
publish trigger.

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
