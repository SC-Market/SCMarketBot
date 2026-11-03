"""Tests for /watchlist add and list in cogs/watchlist.py.

Picking an item from the `query` autocomplete must send its game_item_id, so
the backend matches that exact item; typed text is sent as a text query.
/watchlist list shows the options set on the site (minimum quality, paused).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import watchlist as watchlist_module
from cogs.watchlist import watch_line

ITEM_ID = "58891d96-ea38-4141-831d-eae17e17f7cf"


def _cog():
    return watchlist_module.Watchlist(SimpleNamespace(session=object()))


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1234),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def test_picked_item_is_sent_as_game_item_id():
    assert watchlist_module.watch_request("1", ITEM_ID, 25000) == {
        "discord_id": "1",
        "max_price": 25000,
        "game_item_id": ITEM_ID,
    }


def test_typed_text_is_sent_as_query():
    assert watchlist_module.watch_request("1", "Medical Supplies", 25000) == {
        "discord_id": "1",
        "max_price": 25000,
        "query": "Medical Supplies",
    }


@pytest.mark.asyncio
async def test_autocomplete_offers_game_items_with_their_id():
    results = [
        {"name": "Medical Supplies", "type": "Container", "id": ITEM_ID},
        {"name": "medical supplies", "type": "Commodity", "id": "148eaaf6-b15c-4de5-bc65-9c222f2ed81a"},
    ]
    with patch.object(watchlist_module, "public_fetch", AsyncMock(return_value=results)) as fetch:
        choices = await _cog().watchlist_add_query_autocomplete(_interaction(), "medical")

    assert fetch.await_args.args[0] == "/v2/game-items/search"
    assert [(c.name, c.value) for c in choices] == [
        ("Medical Supplies (Container)", ITEM_ID),
        ("medical supplies (Commodity)", "148eaaf6-b15c-4de5-bc65-9c222f2ed81a"),
    ]


@pytest.mark.asyncio
async def test_autocomplete_waits_for_two_characters():
    with patch.object(watchlist_module, "public_fetch", AsyncMock()) as fetch:
        assert await _cog().watchlist_add_query_autocomplete(_interaction(), "m") == []
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_confirms_with_the_item_name_from_the_backend():
    interaction = _interaction()
    backend = {"result": "Success", "item": {"id": "w-1", "query": "Medical Supplies", "game_item_id": ITEM_ID}}
    with patch.object(watchlist_module, "internal_post", AsyncMock(return_value=backend)) as post:
        await _cog().watchlist_add.callback(_cog(), interaction, ITEM_ID, 25000)

    assert post.await_args.kwargs["json"]["game_item_id"] == ITEM_ID
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert "**Medical Supplies**" in embed.description
    assert ITEM_ID not in embed.description
    assert "exact item" in embed.description



def test_watch_line_plain_watch():
    item = {"id": "w-1", "max_price": 25000, "current_lowest": 21500}
    assert watch_line(item) == "Alert when ≤ **25,000 aUEC** (current: 21,500 aUEC)\nID: `w-1`"


def test_watch_line_shows_quality_and_paused():
    item = {"id": "w-2", "max_price": 9000, "min_quality_tier": 3, "paused": True, "current_lowest": None}
    line = watch_line(item)
    assert "**9,000 aUEC**, quality tier 3+" in line
    assert "Paused" in line
    assert "current:" not in line


@pytest.mark.asyncio
async def test_list_fits_the_embed_field_limit_and_links_the_site():
    cog = watchlist_module.Watchlist(SimpleNamespace(session=object()))
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1234),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    items = [{"id": f"w-{i}", "query": f"Item {i}", "max_price": 100 + i} for i in range(30)]
    with patch.object(watchlist_module, "internal_fetch", AsyncMock(return_value={"items": items})):
        await cog.watchlist_list.callback(cog, interaction)
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert len(embed.fields) == 25
    assert "?tab=price-alerts" in embed.fields[-1].value
