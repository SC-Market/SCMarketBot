"""The shared slash-command error handler: one wording for every refusal."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from discord import app_commands

CMD = SimpleNamespace(name="subscribe")

from util import errors


def _interaction(done=False, name="subscribe alerts"):
    return SimpleNamespace(
        command=SimpleNamespace(qualified_name=name),
        user=SimpleNamespace(id=1),
        guild_id=2,
        response=SimpleNamespace(is_done=lambda: done, send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def test_missing_permission_names_it_and_the_place():
    msg = errors.describe_error(_interaction(), app_commands.MissingPermissions(["manage_channels"]))
    assert "**Manage Channels** permission in this Discord server" in msg
    assert "`/subscribe alerts`" in msg
    assert "Ask a server admin" in msg


def test_multiple_missing_permissions_are_joined():
    msg = errors.describe_error(_interaction(), app_commands.MissingPermissions(["administrator", "manage_guild"]))
    assert "**Administrator** and **Manage Server**" in msg


def test_dm_refusal():
    msg = errors.describe_error(_interaction(), app_commands.NoPrivateMessage())
    assert "only works in a server channel" in msg


def test_bot_missing_permission_points_at_the_bot():
    msg = errors.describe_error(_interaction(), app_commands.BotMissingPermissions(["create_private_threads"]))
    assert "The SC Market bot needs the **Create Private Threads** permission" in msg


def test_other_check_failure_keeps_its_text():
    assert errors.describe_error(_interaction(), app_commands.CheckFailure("Staff only")) == "❌ Staff only"


def test_unexpected_error_is_generic_with_support_hint():
    msg = errors.describe_error(_interaction(), app_commands.CommandInvokeError(CMD, RuntimeError("boom")))
    assert msg.startswith("❌ Something went wrong running `/subscribe alerts`")
    assert "boom" not in msg
    assert "discord.gg/scmarket" in msg


def test_no_command_context():
    msg = errors.describe_error(SimpleNamespace(command=None), app_commands.NoPrivateMessage())
    assert "this command only works" in msg


@pytest.mark.asyncio
async def test_handler_replies_ephemerally_before_and_after_defer():
    fresh = _interaction(done=False)
    await errors.on_app_command_error(fresh, app_commands.MissingPermissions(["manage_channels"]))
    assert fresh.response.send_message.await_args.kwargs["ephemeral"] is True

    deferred = _interaction(done=True)
    await errors.on_app_command_error(deferred, app_commands.NoPrivateMessage())
    assert deferred.followup.send.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_handler_reports_unexpected_errors_but_not_refusals():
    with patch.object(errors.Config, "BUGSNAG_API_KEY", "k"), patch.object(errors.bugsnag, "notify") as notify:
        await errors.on_app_command_error(_interaction(), app_commands.MissingPermissions(["manage_channels"]))
        notify.assert_not_called()
        boom = RuntimeError("boom")
        await errors.on_app_command_error(_interaction(), app_commands.CommandInvokeError(CMD, boom))
        assert notify.call_args.args[0] is boom


def _unknown_interaction():
    import discord
    response = SimpleNamespace(status=404, reason="Not Found")
    return discord.NotFound(response, {"code": 10062, "message": "Unknown interaction"})


def test_expired_interaction_is_recognised_bare_and_wrapped():
    expired = _unknown_interaction()
    assert errors.is_expired_interaction(expired)
    assert errors.is_expired_interaction(app_commands.CommandInvokeError(CMD, expired))
    assert not errors.is_expired_interaction(RuntimeError("boom"))


@pytest.mark.asyncio
async def test_expired_interaction_is_logged_not_reported_or_answered():
    interaction = _interaction()
    with patch.object(errors.Config, "BUGSNAG_API_KEY", "k"), patch.object(errors.bugsnag, "notify") as notify:
        await errors.on_app_command_error(interaction, app_commands.CommandInvokeError(CMD, _unknown_interaction()))
    notify.assert_not_called()
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_ephemeral_swallows_an_expired_interaction():
    interaction = _interaction()
    interaction.response.send_message.side_effect = _unknown_interaction()
    await errors.send_ephemeral(interaction, "hi")  # does not raise


@pytest.mark.asyncio
async def test_private_reply_after_public_defer_deletes_the_thinking_message():
    interaction = _interaction(done=True)
    interaction.delete_original_response = AsyncMock()
    await errors.send_private_after_public_defer(interaction, "nope")
    interaction.delete_original_response.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
