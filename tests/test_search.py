"""/search: query and/or seller, and the seller picker."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import search as search_module

Search = search_module.Search


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


async def _search(interaction, **kwargs):
    defaults = dict(query=None, seller=None, item_type=None, sorting=None, quantity_available=1,
                    min_cost=0, max_cost=0, quality_min=None, quality_max=None)
    defaults.update(kwargs)
    await Search.search.callback(Search(SimpleNamespace(session=None)), interaction, **defaults)


@pytest.mark.asyncio
async def test_needs_a_query_or_a_seller():
    interaction = _interaction()
    with patch.object(search_module, "public_fetch", AsyncMock()) as fetch:
        await _search(interaction, query="  ")
    fetch.assert_not_awaited()
    assert interaction.response.send_message.await_args.kwargs == {"ephemeral": True}


@pytest.mark.asyncio
async def test_seller_alone_lists_that_shop():
    interaction = _interaction()
    with patch.object(search_module, "public_fetch", AsyncMock(return_value={"listings": []})) as fetch:
        await _search(interaction, seller="SCMarket")
    params = fetch.await_args.kwargs["params"]
    assert params["shop_slug"] == "scmarket"
    assert "text" not in params
    assert "Pick the seller from the suggestions" in interaction.followup.send.await_args.args[0]


def test_params_combine_query_seller_and_filters():
    params = search_module.search_params("Gown", "alpha-shop", "armor", "price", 2, 10, 500, 2, 4)
    assert params == {
        "text": "Gown", "shop_slug": "alpha-shop", "item_type": "armor",
        "sort_by": "price", "sort_order": "asc", "quantity_min": 2,
        "price_min": 10, "price_max": 500, "quality_tier_min": 2, "quality_tier_max": 4,
        "page": 1, "page_size": 25,
    }


def test_seller_choices_name_the_owner():
    org = search_module.seller_choice(
        {"slug": "scmarket", "name": "SC Market", "owner": {"type": "contractor", "slug": "SCMARKET"}}
    )
    assert (org.name, org.value) == ("SC Market · org SCMARKET", "scmarket")
    user = search_module.seller_choice(
        {"slug": "khuzdul-shop", "name": "Khuzdul's Wares", "owner": {"type": "user", "slug": "Khuzdul"}}
    )
    assert (user.name, user.value) == ("Khuzdul's Wares · Khuzdul", "khuzdul-shop")
    long = search_module.seller_choice({"slug": "x", "name": "N" * 200})
    assert len(long.name) <= 100
