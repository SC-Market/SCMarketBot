"""/listing price|stock|import: backend calls and replies."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from discord import app_commands

from cogs import listing as listing_module

Listing = listing_module.Listing


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1234),
        response=SimpleNamespace(send_message=AsyncMock(), is_done=lambda: False),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _cog():
    return Listing(SimpleNamespace(session=object()))


def _mode(value):
    return next(c for c in listing_module.STOCK_MODE_CHOICES if c.value == value)


# Picker payload with a stale cached quantity (q=10) to prove it is not used.
LISTING = json.dumps({"l": "listing-uuid", "t": "Medical Gown", "q": 10, "p": 4000})


@pytest.mark.asyncio
@pytest.mark.parametrize("mode, route", [("set", "set"), ("add", "add"), ("subtract", "sub")])
async def test_stock_modes_use_the_backend_quantities(mode, route):
    interaction = _interaction()
    backend = {"result": "Success", "previous_quantity": 7, "quantity": 12}
    with patch.object(listing_module, "internal_post", AsyncMock(return_value=backend)) as post:
        await Listing.stock.callback(_cog(), interaction, "_ME", LISTING, _mode(mode), 5)

    assert post.await_args.args[0] == f"/threads/market/quantity/{route}"
    assert post.await_args.kwargs["json"] == {"quantity": 5, "listing_id": "listing-uuid", "discord_id": "1234"}
    message = interaction.response.send_message.await_args.args[0]
    assert "changed from `7` to `12`" in message
    assert "`10`" not in message
    assert "/listing view" in message


@pytest.mark.asyncio
async def test_stock_backend_error_is_private():
    interaction = _interaction()
    with patch.object(listing_module, "internal_post", AsyncMock(return_value={"error": "Listing not found"})):
        await Listing.stock.callback(_cog(), interaction, "_ME", LISTING, _mode("add"), 5)
    interaction.response.send_message.assert_awaited_once_with("❌ Listing not found", ephemeral=True)


@pytest.mark.asyncio
async def test_typed_listing_is_refused_with_a_hint():
    interaction = _interaction()
    with patch.object(listing_module, "internal_post", AsyncMock()) as post:
        await Listing.price.callback(_cog(), interaction, "_ME", "Medical Gown", 500)
    post.assert_not_awaited()
    assert "Pick the listing from the suggestions" in interaction.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_price_reply_names_the_old_and_new_price():
    interaction = _interaction()
    with patch.object(listing_module, "internal_post", AsyncMock(return_value={"result": "Success"})) as post:
        await Listing.price.callback(_cog(), interaction, "_ME", LISTING, 5000)
    assert post.await_args.kwargs["json"] == {"discord_id": "1234", "listing_id": "listing-uuid", "price": 5000}
    text = interaction.response.send_message.await_args.args[0]
    assert "updated from `4,000` to `5,000` aUEC" in text


@pytest.mark.asyncio
async def test_price_must_be_positive():
    interaction = _interaction()
    await Listing.price.callback(_cog(), interaction, "_ME", LISTING, 0)
    assert interaction.response.send_message.await_args.kwargs == {"ephemeral": True}


def test_uex_mapping_keeps_active_sell_listings_only():
    mapped = listing_module.map_uex_listings([
        {"id": 1, "operation": "sell", "title": "Gown", "price": "500", "in_stock": "3"},
        {"id": 2, "operation": "buy", "title": "Wanted"},
        {"id": 3, "operation": "sell", "is_sold_out": 1, "title": "Gone"},
    ])
    assert [m["uex_id"] for m in mapped] == [1]
    assert mapped[0]["price"] == 500 and mapped[0]["quantity"] == 3


def test_stock_modes_cover_every_backend_route():
    assert set(listing_module.STOCK_MODES.values()) == {"set", "add", "sub"}
    assert {c.value for c in listing_module.STOCK_MODE_CHOICES} == set(listing_module.STOCK_MODES)
    assert [c.value for c in listing_module.IMPORT_SOURCES] == ["uex"]
    assert all(isinstance(c, app_commands.Choice) for c in listing_module.IMPORT_SOURCES)
