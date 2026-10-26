"""/setup: one guided command that picks the right permission and backend call."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest
from discord import app_commands

from cogs import setup as setup_cog

Setup = setup_cog.Setup


def _interaction(guild_id=10, **perms):
    return SimpleNamespace(
        guild_id=guild_id,
        channel_id=20,
        user=SimpleNamespace(id=30),
        command=SimpleNamespace(qualified_name="setup"),
        permissions=discord.Permissions(**perms),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock(), is_done=lambda: False),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _kind(value):
    return next(c for c in setup_cog.KIND_CHOICES if c.value == value)


async def _run(interaction, kind, org=None):
    register = AsyncMock(return_value=True)
    subscribe = AsyncMock(return_value=True)
    with patch.object(setup_cog, "register", register), \
            patch.object(setup_cog, "create_alert_subscription", subscribe):
        await Setup.setup.callback(Setup(SimpleNamespace()), interaction, _kind(kind), org)
    return register, subscribe


def _reply_text(interaction):
    return interaction.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_threads_need_administrator():
    interaction = _interaction(manage_channels=True)
    register, subscribe = await _run(interaction, "threads")
    register.assert_not_awaited()
    assert "**Administrator** permission" in _reply_text(interaction)


@pytest.mark.asyncio
async def test_threads_for_yourself_register_this_channel():
    interaction = _interaction(administrator=True)
    register, _ = await _run(interaction, "threads")
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    register.assert_awaited_once_with(interaction, "channel", "user", "")


@pytest.mark.asyncio
async def test_threads_for_an_org_register_it_by_spectrum_id():
    interaction = _interaction(administrator=True)
    register, _ = await _run(interaction, "threads", " SCMARKET ")
    register.assert_awaited_once_with(interaction, "channel", "contractor", "SCMARKET")


@pytest.mark.asyncio
async def test_alerts_need_manage_channels():
    interaction = _interaction()
    _, subscribe = await _run(interaction, "alerts", "SCMARKET")
    subscribe.assert_not_awaited()
    assert "**Manage Channels** permission" in _reply_text(interaction)


@pytest.mark.asyncio
async def test_alerts_subscribe_this_channel():
    interaction = _interaction(manage_channels=True)
    _, subscribe = await _run(interaction, "alerts", "SCMARKET")
    subscribe.assert_awaited_once_with(interaction, "SCMARKET")

    personal = _interaction(manage_channels=True)
    _, subscribe = await _run(personal, "alerts", "")
    subscribe.assert_awaited_once_with(personal, None)


@pytest.mark.asyncio
async def test_dm_is_refused_for_channel_setups():
    interaction = _interaction(guild_id=None, administrator=True)
    register, _ = await _run(interaction, "threads")
    register.assert_not_awaited()
    assert "only works in a server channel" in _reply_text(interaction)


@pytest.mark.asyncio
async def test_webhook_explains_the_steps_without_any_permission():
    interaction = _interaction()
    register, subscribe = await _run(interaction, "webhook")
    register.assert_not_awaited()
    subscribe.assert_not_awaited()
    embed = interaction.response.send_message.await_args.kwargs["embed"]
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    steps = embed.fields[0].value
    assert "Copy Webhook URL" in steps and "**Webhooks** section" in steps


def test_choice_labels_fit_discord_limits():
    assert {c.value for c in setup_cog.KIND_CHOICES} == set(setup_cog.REQUIRED_PERMISSIONS)
    assert all(len(c.name) <= 100 for c in setup_cog.KIND_CHOICES)
