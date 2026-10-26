"""/register: permission checks, payload, and the success text."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from cogs import registration as reg

Cog = reg.Registration
COMMANDS = [Cog.contractor_channel, Cog.user_channel, Cog.contractor_server, Cog.user_server]


def _interaction(guild_id=111, **perms):
    done = MagicMock(return_value=False)

    async def defer(**_):
        done.return_value = True

    return SimpleNamespace(
        guild_id=guild_id,
        guild=SimpleNamespace(id=guild_id),
        channel=SimpleNamespace(id=222),
        user=SimpleNamespace(id=333),
        permissions=discord.Permissions(**perms),
        response=SimpleNamespace(defer=AsyncMock(side_effect=defer), is_done=done),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _check(command, interaction):
    for check in command.checks:
        assert check(interaction)


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.qualified_name)
def test_requires_administrator(command):
    _check(command, _interaction(administrator=True))
    with pytest.raises(app_commands.MissingPermissions):
        _check(command, _interaction(manage_channels=True))
    with pytest.raises(app_commands.NoPrivateMessage):
        _check(command, _interaction(guild_id=None, administrator=True))


def test_channel_registration_also_sets_its_server():
    # Thread creation looks the channel up inside the official server, so a
    # channel in a different server could never work.
    assert reg.registration_payload(_interaction(), "channel") == {
        "discord_id": "333", "channel_id": "222", "server_id": "111",
    }
    assert reg.registration_payload(_interaction(), "server") == {
        "discord_id": "333", "channel_id": None, "server_id": "111",
    }


def test_endpoint_quotes_the_spectrum_id():
    assert reg._registration_endpoint("contractor", "../user").endswith("/register/contractor/..%2Fuser")
    assert reg._registration_endpoint("user", "").endswith("/register/user")
    with pytest.raises(ValueError):
        reg._registration_endpoint("contractor", "  ")


def test_success_message_says_what_happens_next():
    msg = reg.success_message("channel", "contractor", "SCMARKET")
    assert "the org **SCMARKET**" in msg
    assert "private thread in this channel" in msg
    assert "Create Private Threads" in msg
    assert "/subscribe alerts SCMARKET" in msg
    assert "/subscribe alerts_user" in reg.success_message("server", "user", "")


def _session(status, text):
    resp = MagicMock(status=status, ok=200 <= status < 300)
    resp.text = AsyncMock(return_value=text)
    resp_cm = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=False))
    session = MagicMock()
    session.post = MagicMock(return_value=resp_cm)
    session_cm = MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=False))
    return session, session_cm


@pytest.mark.asyncio
async def test_register_defers_then_posts_and_confirms():
    interaction = _interaction(administrator=True)
    session, session_cm = _session(200, '{"result": "Success"}')
    with patch.object(reg.aiohttp, "ClientSession", return_value=session_cm):
        ok = await reg.register(interaction, "channel", "user")
    assert ok is True
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert session.post.call_args.kwargs["json"]["server_id"] == "111"
    assert "✅ Registered this channel for you." in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_register_surfaces_backend_refusal():
    interaction = _interaction(administrator=True)
    interaction.response.is_done.return_value = True
    _, session_cm = _session(403, '{"error": "You need the Manage Webhooks permission"}')
    with patch.object(reg.aiohttp, "ClientSession", return_value=session_cm):
        ok = await reg.register(interaction, "channel", "contractor", "SCMARKET")
    assert ok is False
    interaction.followup.send.assert_awaited_once_with("❌ You need the Manage Webhooks permission", ephemeral=True)


def test_missing_bot_permissions_for_text_and_forum_channels():
    none = discord.Permissions.none()
    assert reg.missing_bot_permissions(none, discord.ChannelType.text) == [
        "View Channel", "Create Private Threads", "Send Messages In Threads", "Create Invite",
    ]
    forum = reg.missing_bot_permissions(discord.Permissions(view_channel=True), discord.ChannelType.forum)
    assert forum == ["Send Messages", "Send Messages In Threads", "Create Invite"]
    full = discord.Permissions(view_channel=True, create_private_threads=True,
                               send_messages_in_threads=True, create_instant_invite=True)
    assert reg.missing_bot_permissions(full, discord.ChannelType.text) == []
    assert reg.missing_bot_permissions(None, discord.ChannelType.text) == []


@pytest.mark.asyncio
async def test_register_channel_warns_about_missing_bot_permissions():
    interaction = _interaction(administrator=True)
    interaction.app_permissions = discord.Permissions(view_channel=True)
    interaction.channel.type = discord.ChannelType.text
    _, session_cm = _session(200, "{}")
    with patch.object(reg.aiohttp, "ClientSession", return_value=session_cm):
        assert await reg.register(interaction, "channel", "user") is True
    text = interaction.followup.send.await_args.args[0]
    assert "missing **Create Private Threads**, **Send Messages In Threads**, **Create Invite**" in text
