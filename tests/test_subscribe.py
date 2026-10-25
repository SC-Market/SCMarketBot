"""Tests for the permission checks and unsubscribe payload in cogs/subscribe.py.

Alert subscriptions are per channel, so subscribing or unsubscribing requires
the member's Manage Channels permission in a guild, and /unsubscribe must send
the acting user's discord_id so the backend can authorize the deletion.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from cogs import subscribe as subscribe_module

Cog = subscribe_module.AlertSubscriptions
GATED = [Cog.subscribe_alerts, Cog.subscribe_alerts_user, Cog.unsubscribe_alerts]


def _interaction(guild_id=111, manage_channels=True):
    perms = discord.Permissions(manage_channels=manage_channels)
    return SimpleNamespace(
        guild_id=guild_id,
        channel_id=222,
        user=SimpleNamespace(id=333),
        permissions=perms,
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )


async def _run_checks(command, interaction):
    for check in command.checks:
        result = check(interaction)
        if hasattr(result, "__await__"):
            result = await result
        assert result


@pytest.mark.asyncio
@pytest.mark.parametrize("command", GATED, ids=lambda c: c.qualified_name)
async def test_manage_channels_member_passes(command):
    await _run_checks(command, _interaction())


@pytest.mark.asyncio
@pytest.mark.parametrize("command", GATED, ids=lambda c: c.qualified_name)
async def test_member_without_manage_channels_is_rejected(command):
    with pytest.raises(app_commands.MissingPermissions):
        await _run_checks(command, _interaction(manage_channels=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("command", GATED, ids=lambda c: c.qualified_name)
async def test_dm_is_rejected(command):
    with pytest.raises(app_commands.NoPrivateMessage):
        await _run_checks(command, _interaction(guild_id=None, manage_channels=True))


def _fake_session(status=200, body=None):
    resp = MagicMock()
    resp.status = status
    resp.ok = 200 <= status < 300
    resp.json = AsyncMock(return_value=body or {})
    resp_cm = MagicMock()
    resp_cm.__aenter__ = AsyncMock(return_value=resp)
    resp_cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.delete = MagicMock(return_value=resp_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return session, session_cm


@pytest.mark.asyncio
async def test_unsubscribe_sends_discord_id():
    interaction = _interaction()
    session, session_cm = _fake_session()
    with patch.object(subscribe_module.aiohttp, "ClientSession", return_value=session_cm):
        await Cog.unsubscribe_alerts.callback(Cog(SimpleNamespace()), interaction)

    session.delete.assert_called_once()
    assert session.delete.call_args.args[0].endswith("/alert-subscriptions/222")
    assert session.delete.call_args.kwargs["json"] == {"discord_id": "333"}
    assert "removed" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_unsubscribe_surfaces_backend_403():
    interaction = _interaction()
    _, session_cm = _fake_session(403, {"error": "Only the creator can remove this"})
    with patch.object(subscribe_module.aiohttp, "ClientSession", return_value=session_cm):
        await Cog.unsubscribe_alerts.callback(Cog(SimpleNamespace()), interaction)

    interaction.followup.send.assert_awaited_once_with("❌ Only the creator can remove this", ephemeral=True)
