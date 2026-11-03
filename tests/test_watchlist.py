"""/watchlist list shows the options set on the site (minimum quality, paused)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import watchlist as watchlist_module
from cogs.watchlist import watch_line


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
