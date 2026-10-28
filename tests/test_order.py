"""/order status: acknowledge before the backend call, keep errors private."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs import order as order_module

ORDER = json.dumps({"o": "order-uuid", "t": "Medical Gown x5"})


def _interaction(calls):
    state = {"done": False}

    async def defer(**kwargs):
        calls.append("defer")
        state["done"] = True

    return SimpleNamespace(
        user=SimpleNamespace(id=1234),
        channel=None,
        response=SimpleNamespace(
            send_message=AsyncMock(), defer=AsyncMock(side_effect=defer), is_done=lambda: state["done"]
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        delete_original_response=AsyncMock(),
    )


def _cog():
    return order_module.order(SimpleNamespace(session=object()))


@pytest.mark.asyncio
async def test_defers_before_the_backend_and_replies_publicly():
    calls = []
    interaction = _interaction(calls)

    async def post(*args, **kwargs):
        calls.append("post")
        return {"result": "Success"}

    with patch.object(order_module, "internal_post", post):
        await order_module.order.update_status.callback(_cog(), interaction, "fulfilled", ORDER)
    assert calls == ["defer", "post"]
    interaction.response.defer.assert_awaited_once_with(thinking=True)
    assert "Medical Gown x5" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_backend_error_is_private():
    interaction = _interaction([])
    with patch.object(order_module, "internal_post", AsyncMock(return_value={"error": "Not your order"})):
        await order_module.order.update_status.callback(_cog(), interaction, "fulfilled", ORDER)
    interaction.delete_original_response.assert_awaited_once()
    interaction.followup.send.assert_awaited_once_with("❌ Not your order", ephemeral=True)


@pytest.mark.asyncio
async def test_outside_a_thread_answers_without_deferring():
    interaction = _interaction([])
    with patch.object(order_module, "internal_post", AsyncMock()) as post:
        await order_module.order.update_status.callback(_cog(), interaction, "fulfilled", None)
    post.assert_not_awaited()
    interaction.response.defer.assert_not_awaited()
    assert interaction.response.send_message.await_args.kwargs == {"ephemeral": True}
