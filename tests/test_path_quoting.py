"""User input must never add path segments to backend URLs.

yarl normalizes ``..`` in request paths, so an unquoted value like
``../../channel-setups/1`` interpolated into ``/threads/blueprints/conversion/{id}``
would reach a different internal route.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import blueprint as blueprint_module
from util import fetch

TRAVERSAL = "../../../channel-setups/123456789012"  # 36 chars, contains "-"
VALID_ID = "0b2f6a3e-1c4d-4e5f-8a9b-0c1d2e3f4a5b"


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


async def _conversion(blueprint, search_result):
    cog = blueprint_module.Blueprint(SimpleNamespace(session=object()))
    fetch_mock = AsyncMock(side_effect=lambda url, **kw: search_result if url.endswith("/search") else {"error": "stop"})
    with patch.object(blueprint_module, "internal_fetch", fetch_mock):
        await blueprint_module.Blueprint.blueprint_conversion.callback(cog, _interaction(), blueprint)
    return [c.args[0] for c in fetch_mock.await_args_list]


@pytest.mark.asyncio
async def test_conversion_uses_valid_uuid_directly():
    urls = await _conversion(VALID_ID, {})
    assert urls == [f"/threads/blueprints/conversion/{VALID_ID}"]


@pytest.mark.asyncio
async def test_conversion_treats_non_uuid_as_search_text():
    assert len(TRAVERSAL) == 36 and "-" in TRAVERSAL
    urls = await _conversion(TRAVERSAL, {"blueprints": []})
    # Searched by name (as a query param), never interpolated into the path.
    assert urls == ["/threads/blueprints/search"]


@pytest.mark.asyncio
async def test_conversion_quotes_search_result_id():
    urls = await _conversion("Medical Gown", {"blueprints": [{"blueprint_id": "../x"}]})
    assert urls[-1] == "/threads/blueprints/conversion/..%2Fx"


@pytest.mark.asyncio
async def test_seller_search_sends_text_as_a_query_parameter():
    with patch.object(fetch, "public_fetch", AsyncMock(return_value={"shops": []})) as pf:
        assert await fetch.search_shops("../../admin/users?x=1#y") == []
    assert pf.await_args.args[0] == "/v2/shops"
    assert pf.await_args.kwargs["params"]["search"] == "../../admin/users?x=1#y"


@pytest.mark.asyncio
async def test_channel_setup_paths_quote_the_channel():
    from util import channel_setups

    with patch.object(channel_setups, "request", AsyncMock(return_value=(200, {}))) as req:
        await channel_setups.status("../123")
    assert req.await_args.args == ("GET", "/..%2F123")


@pytest.mark.asyncio
async def test_org_listings_quotes_contractor_id():
    with patch.object(fetch, "internal_fetch", AsyncMock(return_value={"listings": []})) as inf:
        await fetch.get_org_listings("../../../channel-setups/1", 42)
    assert inf.await_args.args[0] == "/threads/user/42/listings/..%2F..%2F..%2Fchannel-setups%2F1"
