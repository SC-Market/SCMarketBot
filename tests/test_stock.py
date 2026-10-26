"""Tests for /stock set|add|sub reply handling in cogs/stock.py.

The backend's POST /threads/market/quantity/:opt returns the authoritative
``previous_quantity`` / ``quantity``; the reply must use those rather than the
listing picker's cached quantity, and backend errors must be ephemeral.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import stock as stock_module


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1234),
        response=SimpleNamespace(send_message=AsyncMock()),
    )


def _cog():
    return stock_module.stock(SimpleNamespace(session=object()))


# Picker payload with a stale cached quantity (q=10) to prove it is not used.
LISTING = json.dumps({"l": "listing-uuid", "t": "Medical Gown", "q": 10})


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["set", "add", "sub"])
async def test_success_reply_uses_backend_quantities(action):
    interaction = _interaction()
    backend = {"result": "Success", "previous_quantity": 7, "quantity": 12}
    with patch.object(stock_module, "internal_post", AsyncMock(return_value=backend)) as post:
        await _cog().handle_stock_change(interaction, action, "_ME", LISTING, 5)

    post.assert_awaited_once()
    assert post.await_args.args[0] == f"/threads/market/quantity/{action}"
    assert post.await_args.kwargs["json"] == {
        "quantity": 5,
        "listing_id": "listing-uuid",
        "discord_id": "1234",
    }

    interaction.response.send_message.assert_awaited_once()
    message = interaction.response.send_message.await_args.args[0]
    assert "changed from `7` to `12`" in message
    assert "buyers will see `12` available" in message
    assert "`10`" not in message


@pytest.mark.asyncio
async def test_backend_error_reply_is_ephemeral():
    interaction = _interaction()
    backend = {"error": "Listing not found"}
    with patch.object(stock_module, "internal_post", AsyncMock(return_value=backend)):
        await _cog().handle_stock_change(interaction, "add", "_ME", LISTING, 5)

    interaction.response.send_message.assert_awaited_once_with("❌ Listing not found", ephemeral=True)
