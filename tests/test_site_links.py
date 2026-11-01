"""Embeds link their sc-market.space page in the title: one site link per message."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from cogs import blueprint as blueprint_module
from cogs import help as help_module
from cogs import marketplace as marketplace_module
from cogs import watchlist as watchlist_module
from cogs.registry import add_cogs
from util.errors import SUPPORT_HINT
from util.site import SITE, site_url

ORDER_ID = "0f1e2d3c-4b5a-4968-8776-655443322110"
ITEM_ID = "dff0ce09-d936-4444-9abe-9ba037f9b314"
BP_ID = "11111111-2222-4333-8444-555555555555"


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1234),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _sent_embed(interaction) -> discord.Embed:
    return interaction.followup.send.await_args.kwargs["embed"]


@pytest_asyncio.fixture
async def bot():
    b = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await add_cogs(b)
    return b


def test_site_url_encodes_segments():
    assert site_url() == SITE == "https://sc-market.space"
    assert site_url("contract", ORDER_ID) == f"{SITE}/contract/{ORDER_ID}"
    assert site_url("wiki", "items", "a/b c") == f"{SITE}/wiki/items/a%2Fb%20c"


def test_support_invite_is_ours():
    assert "https://discord.com/invite/N4Gy8py8J4" in SUPPORT_HINT
    assert "discord.gg/scmarket" not in SUPPORT_HINT


@pytest.mark.asyncio
async def test_help_overview_and_detail_link_the_site(bot):
    cog = help_module.Help(bot)
    assert cog._overview_embed().url == SITE
    assert cog._detail_embed("setup").url == SITE


@pytest.mark.asyncio
async def test_order_placed_links_the_order():
    modal = marketplace_module.BuyModal(SimpleNamespace(session=object()), "listing-1", "Medical Gown", 4000)
    modal.quantity._value = "2"
    modal.note._value = ""
    interaction = _interaction()
    backend = {"result": "Success", "order_id": ORDER_ID}
    with patch.object(marketplace_module, "internal_post", AsyncMock(return_value=backend)):
        await modal.on_submit(interaction)
    assert _sent_embed(interaction).url == f"{SITE}/contract/{ORDER_ID}"


@pytest.mark.asyncio
async def test_offer_sent_links_the_offer():
    modal = marketplace_module.OfferModal(SimpleNamespace(session=object()), "listing-1", "Medical Gown")
    modal.offer_amount._value = "45000"
    modal.quantity._value = "1"
    modal.message._value = ""
    interaction = _interaction()
    backend = {"result": "Success", "session_id": "sess-1"}
    with patch.object(marketplace_module, "internal_post", AsyncMock(return_value=backend)):
        await modal.on_submit(interaction)
    assert _sent_embed(interaction).url == f"{SITE}/offer/sess-1"


@pytest.mark.asyncio
async def test_blueprint_conversion_links_the_blueprint():
    cog = blueprint_module.Blueprint(SimpleNamespace(session=object()))
    interaction = _interaction()
    backend = {"blueprint_name": "Medical Gown", "output_item": "Gown", "output_quantity": 1, "ingredients": []}
    with patch.object(blueprint_module, "internal_fetch", AsyncMock(return_value=backend)):
        await cog.blueprint_conversion.callback(cog, interaction, BP_ID)
    assert _sent_embed(interaction).url == f"{SITE}/blueprints/{BP_ID}"


@pytest.mark.asyncio
async def test_watchlist_add_links_the_exact_item_only():
    cog = watchlist_module.Watchlist(SimpleNamespace(session=object()))
    exact = {"result": "Success", "item": {"id": "w-1", "query": "Gun", "game_item_id": ITEM_ID}}
    phrase = {"result": "Success", "item": {"id": "w-2", "query": "gun", "game_item_id": None}}

    interaction = _interaction()
    with patch.object(watchlist_module, "internal_post", AsyncMock(return_value=exact)):
        await cog.watchlist_add.callback(cog, interaction, ITEM_ID, 25000)
    assert _sent_embed(interaction).url == f"{SITE}/wiki/items/{ITEM_ID}"

    interaction = _interaction()
    with patch.object(watchlist_module, "internal_post", AsyncMock(return_value=phrase)):
        await cog.watchlist_add.callback(cog, interaction, "gun", 25000)
    assert _sent_embed(interaction).url is None
