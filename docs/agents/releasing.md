# Releasing to PyPI

How a `v*` tag becomes an installable `uvx mvgeos`. There is no PyPI token in
this repository. Uploads authenticate through GitHub Actions OIDC against a
PyPI *trusted publisher*, so a leaked repository cannot publish.

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

## PyPI setup — the part only a human can do

PyPI will not accept an upload for a project name until that name exists and
has a pending publisher. Both are account actions; neither can be automated.

1. Create or log into the PyPI account that will own the releases, and enable
   two-factor authentication on it. PyPI requires 2FA for API tokens and for
   adding pending publishers.
2. Reserve all eight names. Each one gets its own pending publisher:

   | Field | Value |
   | --- | --- |
   | PyPI project | `mvgeos`, `mvgeos-core`, `mvgeos-provider`, `mvgeos-tome`, `mvgeos-runes`, `mvgeos-agent`, `mvgeos-cli`, `mvgeos-gui` |
   | Owner | `IAmNo1Special` |
   | Repository name | `mvgeos` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

The workflow name must be `publish.yml` and the environment must be `pypi`
exactly as written in `.github/workflows/publish.yml`. A mismatch fails the
upload with an OIDC error and nothing is published.

If the names are already claimed by someone else, stop and escalate. Do not
publish under a substitute name.

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

**`publish`** uploads in the derived order, one distribution per step, using
`UV_PUBLISH_TRUSTED_PUBLISHING=always`. The `always` setting is deliberate: the
default is `automatic`, which would quietly fall back to an ambient token if
OIDC were unavailable. Publishing must fail loudly instead.

`UV_PUBLISH_CHECK_URL=https://pypi.org/simple` makes a re-run after a partial
failure skip whatever already landed. PyPI versions are immutable, so without
this a retry after uploading four of eight packages would fail on the first.

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
