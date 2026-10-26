"""/setup threads|alerts|webhook|status|remove: permissions, backend calls and replies."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from cogs import setup as setup_cog
from util import channel_setups

Setup = setup_cog.Setup
GATED = [Setup.threads, Setup.alerts, Setup.remove]


def _interaction(guild_id=111, app_permissions=None, channel_type=discord.ChannelType.text, **perms):
    return SimpleNamespace(
        guild_id=guild_id,
        channel_id=222,
        channel=SimpleNamespace(id=222, type=channel_type),
        user=SimpleNamespace(id=333),
        command=SimpleNamespace(qualified_name="setup"),
        permissions=discord.Permissions(**perms),
        app_permissions=app_permissions,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _cog():
    return Setup(SimpleNamespace(session=None))


def _check(command, interaction):
    for check in command.checks:
        assert check(interaction)


def _kind(value):
    return next(c for c in setup_cog.KIND_CHOICES if c.value == value)


ALL_BOT_PERMS = discord.Permissions.all()


@pytest.mark.parametrize("command", GATED, ids=lambda c: c.qualified_name)
def test_needs_manage_channels_in_a_server(command):
    _check(command, _interaction(manage_channels=True))
    # Lowered from Administrator: threads and alerts share one rule.
    with pytest.raises(app_commands.MissingPermissions) as err:
        _check(command, _interaction(manage_messages=True))
    assert err.value.missing_permissions == ["manage_channels"]
    with pytest.raises(app_commands.NoPrivateMessage):
        _check(command, _interaction(guild_id=None, manage_channels=True))


def test_status_needs_a_server_but_no_permission():
    _check(Setup.status, _interaction())
    with pytest.raises(app_commands.NoPrivateMessage):
        _check(Setup.status, _interaction(guild_id=None))
    assert Setup.webhook.checks == []


def _backend(status=200, body=None):
    return patch.object(channel_setups, "request", AsyncMock(return_value=(status, body or {})))


@pytest.mark.asyncio
async def test_threads_for_an_org_posts_this_channel_and_server():
    interaction = _interaction(manage_channels=True, app_permissions=ALL_BOT_PERMS)
    body = {"data": {"owner_label": "SC Market (SCMARKET)", "moved_from": {"guild_id": "1", "channel_id": "999"}}}
    with _backend(200, body) as req:
        await Setup.threads.callback(_cog(), interaction, " SCMARKET ")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert req.await_args.args == ("POST", "", {
        "kind": "threads", "discord_id": "333", "channel_id": "222", "guild_id": "111", "spectrum_id": "SCMARKET",
    })
    text = interaction.followup.send.await_args.args[0]
    assert "✅ Order threads for **SC Market (SCMARKET)** now open in this channel." in text
    assert "<#999>" in text
    assert "missing" not in text


@pytest.mark.asyncio
async def test_threads_for_yourself_sends_no_org_and_warns_about_bot_permissions():
    interaction = _interaction(manage_channels=True, app_permissions=discord.Permissions(view_channel=True))
    with _backend(200, {"data": {"owner_label": "khuzdul", "moved_from": None}}) as req:
        await Setup.threads.callback(_cog(), interaction, "")

    assert "spectrum_id" not in req.await_args.args[2]
    text = interaction.followup.send.await_args.args[0]
    assert text.startswith("✅ Order threads for you now open")
    assert "missing **Create Private Threads**, **Send Messages In Threads**, **Create Invite**" in text


@pytest.mark.asyncio
async def test_backend_refusal_is_shown_as_is():
    interaction = _interaction(manage_channels=True)
    error = "You need the Manage Webhooks permission in SC Market on SC Market to set up its order threads."
    with _backend(403, {"error": error}):
        await Setup.threads.callback(_cog(), interaction, "SCMARKET")
    interaction.followup.send.assert_awaited_once_with(f"❌ {error}", ephemeral=True)


@pytest.mark.asyncio
async def test_unreachable_backend_says_so():
    interaction = _interaction(manage_channels=True)
    with _backend(0, {"error": channel_setups.UNREACHABLE}):
        await Setup.alerts.callback(_cog(), interaction, None)
    assert interaction.followup.send.await_args.args[0] == f"❌ {channel_setups.UNREACHABLE}"


@pytest.mark.asyncio
async def test_alerts_reply_explains_claiming():
    interaction = _interaction(manage_channels=True, app_permissions=ALL_BOT_PERMS)
    with _backend(200, {"data": {"owner_label": "SC Market (SCMARKET)"}}) as req:
        await Setup.alerts.callback(_cog(), interaction, "SCMARKET")
    assert req.await_args.args[2]["kind"] == "alerts"
    kwargs = interaction.followup.send.await_args.kwargs
    assert interaction.followup.send.await_args.args == (None,)
    assert "**SC Market (SCMARKET)**" in kwargs["embed"].description
    assert "Claim Orders" in kwargs["embed"].fields[0].value


def test_personal_alerts_have_no_claim_button():
    embed = setup_cog.alerts_embed("khuzdul", None)
    assert "offers sent to you" in embed.description
    assert "no Claim button" in embed.fields[0].value


@pytest.mark.asyncio
async def test_webhook_explains_the_steps_without_any_permission():
    interaction = _interaction()
    await Setup.webhook.callback(_cog(), interaction)
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs["ephemeral"] is True
    steps = kwargs["embed"].fields[0].value
    assert "Copy Webhook URL" in steps and "**Webhooks** section" in steps


@pytest.mark.asyncio
async def test_status_lists_each_owner_and_how_to_stop_it():
    interaction = _interaction(app_permissions=ALL_BOT_PERMS)
    setups = [
        {"owner_type": "org", "owner_label": "SC Market (SCMARKET)", "spectrum_id": "SCMARKET", "threads": True, "alerts": True},
        {"owner_type": "user", "owner_label": "khuzdul", "spectrum_id": None, "threads": False, "alerts": True},
        {"owner_type": "shop", "owner_label": "the shop Khuzdul's Wares", "spectrum_id": None, "threads": True, "alerts": False},
    ]
    with _backend(200, {"data": setups}) as req:
        await Setup.status.callback(_cog(), interaction)
    assert req.await_args.args == ("GET", "/222")
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert [f.name for f in embed.fields] == [
        "For SC Market (SCMARKET)", "For khuzdul", "For the shop Khuzdul's Wares",
    ]
    assert embed.fields[0].value.startswith("Order threads and order alerts")
    assert "`org:SCMARKET`" in embed.fields[0].value
    assert "leaving `org` empty" in embed.fields[1].value
    assert "Shop's Settings › Discord" in embed.fields[2].value.replace("shop's", "Shop's")


@pytest.mark.asyncio
async def test_status_of_an_empty_channel_points_at_setup():
    interaction = _interaction()
    with _backend(200, {"data": []}):
        await Setup.status.callback(_cog(), interaction)
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Nothing is set up in this channel"
    assert "/setup threads" in embed.description and "/setup alerts" in embed.description


@pytest.mark.asyncio
async def test_status_warns_when_the_bot_cannot_post_alerts():
    interaction = _interaction(app_permissions=discord.Permissions(view_channel=True))
    with _backend(200, {"data": [{"owner_type": "user", "owner_label": "k", "threads": False, "alerts": True}]}):
        await Setup.status.callback(_cog(), interaction)
    assert "missing **Send Messages**, **Embed Links**" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_remove_sends_kind_and_org():
    interaction = _interaction(manage_channels=True)
    with _backend(200, {"data": {"kind": "alerts", "owner_label": "SC Market (SCMARKET)"}}) as req:
        await Setup.remove.callback(_cog(), interaction, _kind("alerts"), "SCMARKET")
    assert req.await_args.args == ("DELETE", "/222", {"kind": "alerts", "discord_id": "333", "spectrum_id": "SCMARKET"})
    text = interaction.followup.send.await_args.args[0]
    assert text.startswith("✅ This channel no longer gets order alerts for **SC Market (SCMARKET)**.")


@pytest.mark.asyncio
async def test_remove_shows_what_the_channel_has_when_nothing_matches():
    interaction = _interaction(manage_channels=True)
    error = "This channel has no order threads for you. It has: order alerts for SC Market (SCMARKET)."
    with _backend(404, {"error": error}):
        await Setup.remove.callback(_cog(), interaction, _kind("threads"), None)
    interaction.followup.send.assert_awaited_once_with(f"❌ {error}", ephemeral=True)


def test_missing_bot_permissions_per_channel_type_and_kind():
    none = discord.Permissions.none()
    assert setup_cog.missing_bot_permissions(none, discord.ChannelType.text) == [
        "View Channel", "Create Private Threads", "Send Messages In Threads", "Create Invite",
    ]
    forum = setup_cog.missing_bot_permissions(discord.Permissions(view_channel=True), discord.ChannelType.forum)
    assert forum == ["Send Messages", "Send Messages In Threads", "Create Invite"]
    assert setup_cog.missing_bot_permissions(none, discord.ChannelType.text, "alerts") == [
        "View Channel", "Send Messages", "Embed Links",
    ]
    assert setup_cog.missing_bot_permissions(None, discord.ChannelType.text) == []


@pytest.mark.asyncio
async def test_request_reports_an_unreachable_backend():
    session_cm = MagicMock(__aenter__=AsyncMock(side_effect=channel_setups.aiohttp.ClientError("down")),
                           __aexit__=AsyncMock(return_value=False))
    with patch.object(channel_setups.aiohttp, "ClientSession", return_value=session_cm):
        status, body = await channel_setups.request("GET", "/1")
    assert status == 0 and body["error"] == channel_setups.UNREACHABLE
