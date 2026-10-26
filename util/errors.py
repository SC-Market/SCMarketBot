"""One place that turns slash-command failures into clear, ephemeral replies.

Registered as the command tree's ``on_error`` in ``main.py``, so every cog gets
the same refusal wording: it names the missing permission, says where it is
needed (this Discord server vs. your SC Market org), and what to do next.
Cogs should raise ``app_commands`` check errors instead of writing their own.
"""
import logging

import bugsnag
import discord
from discord import app_commands

from util.config import Config

logger = logging.getLogger("SCMarketBot.Errors")

SUPPORT_HINT = "If it keeps happening, ask in the SC Market Discord: https://discord.gg/scmarket"


def _perm_label(name: str) -> str:
    """``manage_channels`` -> ``Manage Channels`` (also handles ``guild`` -> ``Server``)."""
    return name.replace("_", " ").replace("guild", "server").title()


def command_label(interaction) -> str:
    command = getattr(interaction, "command", None)
    name = getattr(command, "qualified_name", None)
    return f"`/{name}`" if name else "this command"


def describe_error(interaction, error: app_commands.AppCommandError) -> str:
    """User-facing text for a failed command. Pure, so it is unit-tested."""
    cmd = command_label(interaction)

    if isinstance(error, app_commands.NoPrivateMessage):
        return f"❌ {cmd} only works in a server channel, not in DMs. Run it in the channel you want to set up."

    if isinstance(error, app_commands.MissingPermissions):
        perms = " and ".join(f"**{_perm_label(p)}**" for p in error.missing_permissions)
        return (
            f"❌ You need the {perms} permission in this Discord server to use {cmd}.\n"
            "-# Ask a server admin to run it, or to give you that permission."
        )

    if isinstance(error, app_commands.BotMissingPermissions):
        perms = " and ".join(f"**{_perm_label(p)}**" for p in error.missing_permissions)
        return (
            f"❌ The SC Market bot needs the {perms} permission in this channel for {cmd}.\n"
            "-# A server admin can grant it in the channel's settings under Permissions."
        )

    if isinstance(error, app_commands.CommandOnCooldown):
        return f"❌ {cmd} is on cooldown. Try again in {error.retry_after:.0f}s."

    if isinstance(error, app_commands.CheckFailure):
        detail = str(error).strip()
        return f"❌ {detail}" if detail else f"❌ You can't use {cmd} here."

    return f"❌ Something went wrong running {cmd}. Please try again.\n-# {SUPPORT_HINT}"


async def send_ephemeral(interaction: discord.Interaction, message: str = None, **kwargs) -> None:
    """Reply privately whether or not the interaction was already answered/deferred."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True, **kwargs)
        else:
            await interaction.response.send_message(message, ephemeral=True, **kwargs)
    except discord.HTTPException:
        logger.error("Failed to send a reply to the user", exc_info=True)


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """``CommandTree.on_error`` handler shared by every cog."""
    root = error.original if isinstance(error, app_commands.CommandInvokeError) else error
    command = getattr(interaction.command, "qualified_name", None)

    if isinstance(error, app_commands.CheckFailure):
        logger.info("command_refused name=%s reason=%s", command, type(error).__name__)
    else:
        logger.error("command_failed name=%s", command, exc_info=root)
        if Config.BUGSNAG_API_KEY:
            bugsnag.notify(
                root if isinstance(root, Exception) else Exception(str(root)),
                context=f"/{command}" if command else "app command",
                meta_data={
                    # No user id: error reports are anonymous (SC Market privacy policy).
                    "discord": {
                        "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
                        "command": command,
                    }
                },
            )

    await send_ephemeral(interaction, describe_error(interaction, error))
