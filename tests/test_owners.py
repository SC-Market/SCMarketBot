"""The shared owner picker for /stock, /price and /list."""
import json

import pytest

from util.owners import ME, build_owner_choices, parse_owner

ORGS = [
    {"name": "SC Market", "spectrum_id": "SCMARKET"},
    {"name": "Test Squadron", "spectrum_id": "TEST"},
]


@pytest.mark.parametrize("value", [None, "", "  ", ME, "me", "Me", "ME"])
def test_blank_or_me_means_yourself(value):
    assert parse_owner(value) is None


def test_autocomplete_payload_resolves_to_spectrum_id():
    assert parse_owner(json.dumps({"s": "SCMARKET", "n": "SC Market"})) == "SCMARKET"


def test_typed_spectrum_id_is_accepted():
    # Previously a typed org made /list silently create a personal listing.
    assert parse_owner(" SCMARKET ") == "SCMARKET"


def test_payload_without_spectrum_id_means_yourself():
    assert parse_owner(json.dumps({"n": "x"})) is None


def test_choices_filter_and_always_offer_me():
    choices = build_owner_choices(ORGS, "test")
    assert [c.name for c in choices] == ["Test Squadron (TEST)", "Me"]
    assert parse_owner(choices[0].value) == "TEST"
    assert choices[-1].value == ME


def test_choices_survive_unlinked_user_response():
    # get_user_orgs returns the raw response dict when the user isn't linked.
    assert [c.name for c in build_owner_choices({"error": "not linked"}, "")] == ["Me"]


def test_choices_are_capped_for_discord():
    many = [{"name": f"Org {i}", "spectrum_id": f"O{i}"} for i in range(40)]
    assert len(build_owner_choices(many, "")) == 25
