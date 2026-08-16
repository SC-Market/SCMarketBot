"""Unit tests for the pure thread-planning decision logic.

These cover the two production incidents that dead-lettered order notifications:
  * a forum channel configured as the thread channel (was a TypeError crash-loop);
  * an empty members list (was wrongly rejected as a missing field).
"""
import pytest

from util.thread_planning import (
    STRATEGY_FORUM,
    STRATEGY_TEXT,
    STRATEGY_UNSUPPORTED,
    build_thread_name,
    plan_thread_creation,
    validate_create_thread_fields,
)


class _FakeChannelType:
    """Stand-in for discord.ChannelType (only ``.name`` is used)."""

    def __init__(self, name):
        self.name = name


# --- validate_create_thread_fields -----------------------------------------

def test_validate_passes_with_server_and_channel():
    assert validate_create_thread_fields("123", "456") is None


def test_validate_allows_empty_members_case():
    # Regression: members list is not part of validation, so an offer with no
    # linked Discord users still passes (the thread is created for admins).
    assert validate_create_thread_fields("123", "456") is None


@pytest.mark.parametrize(
    "server_id,channel_id",
    [(None, "456"), ("123", None), ("", ""), (None, None)],
)
def test_validate_fails_when_destination_missing(server_id, channel_id):
    err = validate_create_thread_fields(server_id, channel_id)
    assert err is not None
    assert "create_thread" in err


# --- plan_thread_creation ---------------------------------------------------

def test_plan_forum_channel():
    # Regression: forum channels must NOT take the text/private-thread path,
    # which raised `ForumChannel.create_thread() got an unexpected keyword 'type'`.
    assert plan_thread_creation(_FakeChannelType("forum")) == STRATEGY_FORUM


@pytest.mark.parametrize("name", ["text", "news"])
def test_plan_text_like_channels(name):
    assert plan_thread_creation(_FakeChannelType(name)) == STRATEGY_TEXT


@pytest.mark.parametrize("name", ["voice", "category", "stage_voice", "forum_media"])
def test_plan_unsupported_channels(name):
    assert plan_thread_creation(_FakeChannelType(name)) == STRATEGY_UNSUPPORTED


def test_plan_accepts_plain_string():
    assert plan_thread_creation("forum") == STRATEGY_FORUM
    assert plan_thread_creation("text") == STRATEGY_TEXT


# --- build_thread_name ------------------------------------------------------

def test_build_thread_name_for_order():
    name = build_thread_name({"order_id": "5e9fc632-9716-4e1a", "id": "5e9fc632-9716-4e1a"})
    assert name == "order-5e9fc632"


def test_build_thread_name_for_offer_uses_id():
    name = build_thread_name({"id": "ea5a53f2-6425-426d"})
    assert name == "offer-ea5a53f2"


def test_build_thread_name_handles_missing_ids():
    # Should not raise even when both ids are absent.
    assert build_thread_name({}) == "offer-"
