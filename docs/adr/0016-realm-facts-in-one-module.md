# ADR 0016: Realm Facts in One Module

## Status

Accepted

## Context

ADR-0004 built the Realm abstraction against one provider and deferred the rest.
The moment a second Realm exists, three separate places need the same three facts
about a Realm — which Rune provides it, where its API lives, and what its
credential is called:

- the registry, which has to name the Rune to install when resolution fails;
- the CLI, which prompts with that name and reads the matching credential;
- the GUI, which renders that name on a badge and a transcript message.

They were three separate literals, and each was wrong in the same direction. With
one Realm, a hardcoded `openrouter-realm` in an error message was always right;
with two, it names a Rune the Summoner does not need and the model they do need
goes unresolved with a message that reads as actionable and is not. The same
shape applies to the credential: one variable, `OPENROUTER_API_KEY`, was read for
whatever model was selected, so pointing MvgeOS at a second Realm authenticates at
the wrong host and fails every call with a message naming the model rather than
the credential.

Two further couplings sat underneath those literals:

- **The free tier was read off the name.** `Model.free` accepted any id ending
  `-free`, on top of OpenRouter's `:free`. Reading `-free` globally would let a
  paid model be reported free on the strength of its name, which is the one
  mistake a cost guard must not make.
- **The baseline catalog named no Realm.** `_create_openrouter_model` hardcoded
  `realm="openrouter"` and `base_url=.../openrouter.ai/api/v1`, so a catalog entry
  for a different Realm would have been built as an OpenRouter model and sent to
  openrouter.ai, where it does not exist.

## Decision

Facts about Realms live in one module, `mvgeos_provider/realms.py`, beside the
registry that acts on them, and three consumers read them from there:

- **Tables** record what we ship: `REALM_RUNES`, `REALM_BASE_URLS`,
  `REALM_API_KEY_ENV`, `REALM_FREE_SUFFIXES`.
- **Functions** derive, so a Realm that has no table entry still produces a usable
  answer instead of nothing — `realm_for_model_id`, `rune_for_realm`,
  `api_key_env_for_realm`, `free_suffix_for_realm`. These run on the failure path,
  where returning a blank is the one outcome that leaves a Summoner with no next
  step. `rune_for_realm("")` is deliberately `""` and not the `-realm` the
  convention would produce: it would look like a name, so nothing would catch it.
- **`NoRealmRegisteredError` carries `realm` and `rune_name` as attributes.**
  `no_realm_registered()` builds it. The CLI prompt and the GUI badge read those
  attributes; both used to recover the name by splitting the message on
  `"install "`, which couples a user-facing surface to error wording.
- **An unknown slug under a Realm we ship is a missing Rune, not an unknown
  model.** `_unknown_model_error` distinguishes the two, because they need
  opposite answers and both present as a bare failure. The flip side is
  pre-existing and deliberate: once a Realm *is* registered, any slug under it
  resolves, typo included, because a Rune-provided Realm serves models no catalog
  knows about.

Alongside the tables:

- **Each Realm keeps its own credential** at `~/.agents/auth/<realm>.json`, read
  via `load_api_key_for_realm` and written via `save_api_key_to_auth(…, realm)`.
  Sharing one file would mean installing a second Realm silently overwrites the
  first one's key.
- **`Model.free` gates `-free` on the Realm** that uses the convention, via a
  small set in `mvgeos_core.channel`. core keeps its own copy because it sits
  below the provider layer in the dependency graph.
- **The baseline catalog carries a per-entry Realm.** The value is optional and
  defaults to `openrouter`, which is what every entry written before a second
  Realm existed means, so the shipped file stays valid.

**Which Realm is the default is not decided here.** `DEFAULT_REALM` states the
Realm that serves `DEFAULT_MODEL` and `test_default_realm_agrees_with_the_shipped_catalog`
holds the copy to the shipped catalog, so moving the default is a two-constant
edit that fails CI if only one moves. See ADR-0015 for the default-Realm decision.

## Contract

Symbols this decision commits to. The Realm tables are the single place the
registry, the CLI and the GUI agree on a Rune name, a base URL and a credential
variable; the derivations must keep producing a usable answer for a Realm that is
not in a table, because they run on the failure path.

<!-- adr-contract: REALM_RUNES, REALM_BASE_URLS, REALM_API_KEY_ENV, REALM_FREE_SUFFIXES, DEFAULT_REALM, realm_for_model_id, rune_for_realm, api_key_env_for_realm, free_suffix_for_realm, no_realm_registered, NoRealmRegisteredError, Model.free, load_api_key_for_realm -->

## Consequences

- A second Realm is now a data change plus a Rune: add its row to the tables, add
  its catalog entries with their own Realm, and the CLI, GUI and registry pick it
  up. None of the three carries a literal that has to be found.
- **`opencode/space-bunny-free`'s context window is measured, not stated.** Zen
  publishes no context length — `/zen/v1/models` returns 86 entries carrying only
  `id`, `object`, `created`, `owned_by` — so the number in the catalog has to come
  from probing. Measured 2026-10-06 against
  `POST https://opencode.ai/zen/v1/chat/completions`, with no `Authorization`
  header, the hard
  input ceiling brackets tightly on **1,048,576** (2²⁰): a request of 1,048,465
  prompt tokens was accepted and one of 1,048,765 was rejected with
  `400 invalid_request_error`. Accepted below that point without error at 200,165
  / 1,000,165 / 1,002,165 / 1,010,165 / 1,040,165 tokens; rejected above it at
  1,050,165 / 1,100,165 / 1,250,000 / 1,500,165 / 2,000,165 / 4,000,165.
  The catalog therefore states 1048576, where it previously stated an unverified
  128000 — roughly eight times too low, which is the direction that causes silent
  compaction rather than a visible provider error. Re-measure before trusting it;
  the value is a measurement of one provider on one day, not a published
  specification.
- **Zen's free tier answers with no `Authorization` header at all, and rejects a
  present-but-wrong one.** A keyless `POST` returned `200` with `cost: "0"`, and
  eight keyless calls with a short prompt returned content every time. Sending
  `Authorization: Bearer <anything-wrong>` returns `401 Invalid API key.`, and an
  empty bearer cannot be sent at all — `httpx` rejects the header value locally,
  which surfaces as an opaque `LocalProtocolError` rather than a credential error.
  So the free tier is reachable without a subscription, but only by omitting the
  header, and MvgeOS does not omit it: the CLI refuses to start without a resolved
  key and the Rune sends what it is given. A real `OPENCODE_API_KEY` is still
  required to run Zen. The empty-key case is unreachable through the CLI and GUI,
  which is why the opaque error is noted here rather than fixed.
- Contemplation is unavailable on the Zen free tier. Zen publishes no reasoning
  parameter for it and the standard has no field for it, so the Rune caps output
  tokens instead. Contemplation deltas are still read, so an upstream model that
  thinks out loud lands in the transcript rather than being dropped.
- The `-free` suffix is scoped to a Realm by a set in `mvgeos_core.channel` that
  duplicates the provider layer's table. That duplication is forced by the
  dependency direction — core has zero first-party dependencies and cannot import
  the provider layer — and it is the one place two modules must agree on the same
  fact. `Model.free`'s tests pin both sides.