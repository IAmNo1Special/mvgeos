"""What the engine knows about each Realm, and how it derives the rest.

The tables here are the facts; these tests are what keeps them honest and keep
the derivations from quietly disagreeing with the tables. Every one of them is
about the failure path, because that is where these functions run: a Summoner
who cannot resolve a model needs to be told something they can act on, and the
difference between a useful name and a wrong one is the whole value of the
module.
"""

from __future__ import annotations

import pytest
from mvgeos_core.channel import Model
from mvgeos_core.constants import DEFAULT_MODEL

from mvgeos_provider.base import NoRealmRegisteredError
from mvgeos_provider.model_registry import list_models
from mvgeos_provider.realms import (
    DEFAULT_REALM,
    REALM_API_KEY_ENV,
    REALM_BASE_URLS,
    REALM_FREE_SUFFIXES,
    REALM_RUNES,
    api_key_env_for_realm,
    free_suffix_for_realm,
    realm_for_model_id,
    rune_for_realm,
)
from mvgeos_provider.registry import RealmRegistry, no_realm_registered

# ---------------------------------------------------------------------------
# Deriving a Realm from a slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("opencode/space-bunny-free", "opencode"),
        ("openrouter/free", "openrouter"),
        ("nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia"),
        # No slash: the whole id is the prefix, because there is nothing else it
        # could be. Returning "" here would silently resolve to the wrong Realm.
        ("gpt-5.5", "gpt-5.5"),
        # A trailing slash is not a prefix.
        ("opencode/", "opencode/"),
        ("", ""),
    ],
)
def test_realm_for_model_id(slug: str, expected: str) -> None:
    assert realm_for_model_id(slug) == expected


# ---------------------------------------------------------------------------
# Naming the Rune that provides a Realm
# ---------------------------------------------------------------------------


def test_every_realm_we_ship_names_its_rune() -> None:
    for realm in REALM_RUNES:
        assert rune_for_realm(realm) == REALM_RUNES[realm]


def test_rune_for_an_unknown_realm_follows_the_naming_convention() -> None:
    """A Realm nobody has added to the table still produces a usable name.

    This runs on the failure path, so returning nothing would leave a Summoner
    with no next step -- which is the one outcome the message exists to avoid.
    """
    assert rune_for_realm("groq") == "groq-realm"


def test_rune_for_an_unknown_realm_is_empty() -> None:
    """An unknown Realm must not produce a name that merely looks like one.

    Every caller either prompts or calls install with the result. ``rune_for_realm
    ("")`` returning ``"-realm"`` would hand both a string that reads as a Rune
    and names nothing.
    """
    assert rune_for_realm("") == ""


def test_the_rune_named_for_a_realm_is_one_we_publish() -> None:
    """A derived name must not claim a Rune exists when none does.

    The badge and the install prompt both trust this. Offering ``ollama-realm``
    would send someone to a Rune the marketplace does not have, which is worse
    than saying nothing.
    """
    assert rune_for_realm("ollama") not in REALM_RUNES.values()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_each_realms_key_comes_from_its_own_environment_variable() -> None:
    """Handing one Realm's key to another authenticates at the wrong host.

    The failure that follows names the model rather than the credential, so the
    Summoner is sent looking in the wrong place entirely.
    """
    assert api_key_env_for_realm("opencode") == "OPENCODE_API_KEY"
    assert api_key_env_for_realm("openrouter") == "OPENROUTER_API_KEY"


def test_an_unmapped_realm_key_follows_the_ecosystem_shape() -> None:
    assert api_key_env_for_realm("groq") == "GROQ_API_KEY"
    assert api_key_env_for_realm("") == ""


def test_the_key_environments_are_distinct() -> None:
    """Two Realms sharing a variable name means one silently overwrites the other."""
    assert len(set(REALM_API_KEY_ENV.values())) == len(REALM_API_KEY_ENV)


# ---------------------------------------------------------------------------
# The default model and the default Realm
# ---------------------------------------------------------------------------


def test_default_realm_agrees_with_the_shipped_catalog() -> None:
    """``DEFAULT_REALM`` is a copy, and this is what holds the copy honest.

    It cannot be derived from ``DEFAULT_MODEL``'s slug: for a routed slug like
    ``nvidia/nemotron-3-ultra-550b-a55b:free`` the prefix is the provider and the
    Realm is openrouter. So it is stated, and the statement is checked against the
    catalog that actually ships. Changing ``DEFAULT_MODEL`` without this fails
    here, which is the drift this exists to catch.
    """
    entry = list_models()
    default = next(m for m in entry if m.id == DEFAULT_MODEL)
    assert default.realm == DEFAULT_REALM


def test_the_default_model_is_free() -> None:
    """The default is what a first-time Summoner runs.

    A paid default would mean the documented first run asks for a card, which is
    not what the quickstart promises.
    """
    default = next(m for m in list_models() if m.id == DEFAULT_MODEL)
    assert default.free is True


def test_the_default_model_has_a_base_url_in_the_shipped_catalog() -> None:
    """A baseline entry is read without contacting anyone.

    Before the Rune is installed this is the only base URL there is, so an empty
    one means the catalog cannot tell a Summoner where the model lives.
    """
    default = next(m for m in list_models() if m.id == DEFAULT_MODEL)
    assert default.base_url == REALM_BASE_URLS[DEFAULT_REALM]


# ---------------------------------------------------------------------------
# The error a Summoner actually sees
# ---------------------------------------------------------------------------


def test_the_error_names_the_rune_for_the_models_own_realm() -> None:
    """A model that needs opencode-realm must not be told to install openrouter.

    That was the literal this module replaced: the message is the only remedy
    available, so a hardcoded Rune name is a Rune name that goes stale the moment
    a second Realm exists.
    """
    error = no_realm_registered("opencode/space-bunny-free")
    assert error.rune_name == "opencode-realm"
    assert error.realm == "opencode"
    assert "mvgeos rune install opencode-realm" in str(error)


def test_the_error_carries_the_realm_even_when_the_model_has_none() -> None:
    """A model with no realm set falls back to its id prefix, and says so."""
    model = Model(
        id="opencode/space-bunny-free",
        name="Space Bunny Free",
        realm="",
        base_url="",
        api_key="",
    )
    error = no_realm_registered(model)
    assert error.realm == "opencode"
    assert error.rune_name == "opencode-realm"


def test_the_error_message_and_its_attributes_never_disagree() -> None:
    """The message is prose; the attributes are what callers act on.

    The GUI used to recover the Rune by splitting the message, which is why both
    have to carry the same name.
    """
    error = no_realm_registered("opencode/space-bunny-free")
    assert error.rune_name in str(error)


def test_an_unknown_slug_under_a_realm_names_that_realms_rune() -> None:
    """The missing-Rune and unknown-model cases need opposite answers.

    Installing the Rune is the correct first step for a Summoner who typed a
    valid model on a machine that has not installed its Rune, and it is the
    wrong advice for a Summoner who typed a model that does not exist. Before the
    distinction existed, both got the same message and the second one sent them
    to install something.
    """
    reg = RealmRegistry()
    with pytest.raises(NoRealmRegisteredError) as missing_rune:
        reg.resolve("opencode/space-bunny-free", api_key="k")
    assert missing_rune.value.rune_name == "opencode-realm"

    with pytest.raises(ValueError, match="Unknown model") as unknown:
        reg.resolve("totally-not-a-real-namespace/made-up", api_key="k")
    assert "Unknown model" in str(unknown.value)


def test_a_spellcheck_typo_is_still_reported_as_a_missing_realm() -> None:
    """Named for what a Summoner experiences, not for the tidiness it looks like.

    A typo under a Realm we ship cannot be told apart from a real model we have
    not catalogued -- and the advice is the same either way, because installing
    the Rune is what has to happen before the typo can even be detected.
    """
    reg = RealmRegistry()
    with pytest.raises(NoRealmRegisteredError) as exc:
        reg.resolve("opencode/space-bunny-fre", api_key="k")
    assert exc.value.rune_name == "opencode-realm"


def test_a_registered_realm_still_resolves_an_uncatalogued_slug() -> None:
    """A Rune-provided Realm serves models no catalog knows about.

    Refusing unknown ids under a registered Realm would refuse the feature that
    makes Runes worth having.
    """
    reg = RealmRegistry()
    reg.register_realm_factory(
        "opencode", lambda api_key="", base_url="", **kw: object()
    )
    model, _ = reg.resolve("opencode/a-model-nobody-catalogued", api_key="k")
    assert model.realm == "opencode"


# ---------------------------------------------------------------------------
# Free-model conventions
# ---------------------------------------------------------------------------


def test_each_realm_declares_at_most_one_free_suffix() -> None:
    assert all(suffix for suffix in REALM_FREE_SUFFIXES.values())


def test_free_suffix_is_per_realm_not_global() -> None:
    """Reading ``-free`` off any id would let a name call a paid model free.

    That is the one mistake a cost guard must not make, so the suffix belongs to
    the Realm that actually uses it.
    """
    assert free_suffix_for_realm("opencode") == "-free"
    assert free_suffix_for_realm("openrouter") == ":free"
    assert free_suffix_for_realm("ollama") == ""
