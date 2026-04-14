import json
import logging
import traceback
from urllib.parse import quote

import aiohttp
import bugsnag
import discord
from discord import app_commands
from discord.app_commands import checks
from discord.ext import commands

from util.config import Config

logger = logging.getLogger("SCMarketBot.registration")

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _registration_endpoint(entity: str, name: str) -> str:
    base = Config.discord_backend_base().rstrip("/")
    if entity == "user":
        return f"{base}/register/user"
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValueError("Contractor name or Spectrum ID is required")
    return f"{base}/register/contractor/{quote(trimmed, safe='')}"


def _parse_error_body(text: str, status: int) -> str:
    text = (text or "").strip()
    if not text:
        return f"Registration failed (HTTP {status}). Please try again later."
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except json.JSONDecodeError:
        pass
    if text.startswith("<") or "<pre>" in text:
        if "Cannot POST" in text:
            return (
                "The server could not process this registration request. "
                "Please contact support if this continues."
            )
        return "The registration service returned an unexpected response. Please try again later."
    snippet = text[:300] + ("…" if len(text) > 300 else "")
    return f"Registration failed (HTTP {status}): {snippet}"


async def _send_ephemeral(interaction: discord.Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        logger.error("Failed to send registration feedback to user", exc_info=True)


def _unwrap_app_command_error(error: app_commands.AppCommandError) -> BaseException:
    if isinstance(error, app_commands.CommandInvokeError) and error.original:
        return error.original
    return error


class Registration(commands.GroupCog, name="register"):
    channel = app_commands.Group(
        name="channel",
        description="Register a channel as the channel that will house threads for order fulfillment",
    )
    server = app_commands.Group(
        name="server",
        description="Register a server as the official server for order fulfillment",
    )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        root = _unwrap_app_command_error(error)
        if isinstance(root, app_commands.CheckFailure):
            await _send_ephemeral(interaction, str(root))
            return

        logger.error("Registration command error", exc_info=root)

        if Config.BUGSNAG_API_KEY:
            bugsnag.notify(
                root if isinstance(root, Exception) else Exception(str(root)),
                context="Registration cog",
                meta_data={
                    "discord": {
                        "user_id": str(interaction.user.id),
                        "guild_id": str(interaction.guild.id) if interaction.guild else None,
                        "command": interaction.command.name if interaction.command else None,
                    }
                },
            )
        await _send_ephemeral(
            interaction,
            "Something went wrong with that command. Please try again or contact support.",
        )

    @channel.command(name="contractor")
    @checks.has_permissions(administrator=True)
    @app_commands.describe(name="The Spectrum ID or name of the contractor")
    async def contractor_channel(
        self, interaction: discord.Interaction, name: str
    ):
        """Register a channel as the channel that will house threads for order fulfillment for your contractor. Make sure the bot has permission to see the channel and make private threads there."""
        await self.register(interaction, "channel", "contractor", name)

    @channel.command(name="user")
    @checks.has_permissions(administrator=True)
    async def user_channel(self, interaction: discord.Interaction):
        """Register a channel as the channel that will house threads for order fulfillment for your user. Make sure the bot has permission to see the channel and make private threads there."""
        await self.register(interaction, "channel", "user")

    @server.command(name="contractor")
    @checks.has_permissions(administrator=True)
    @app_commands.describe(name="The Spectrum ID or name of the contractor")
    async def contractor_server(
        self, interaction: discord.Interaction, name: str
    ):
        """Register a server as the official server for order fulfillment for your contractor."""
        await self.register(interaction, "server", "contractor", name)

    @server.command(name="user")
    @checks.has_permissions(administrator=True)
    async def user_server(self, interaction: discord.Interaction):
        """Register a server as the official server for order fulfillment for your user."""
        await self.register(interaction, "server", "user")

    @staticmethod
    async def register(
        interaction: discord.Interaction,
        reg_type: str,
        entity: str,
        name: str = "",
    ):
        try:
            url = _registration_endpoint(entity, name)
        except ValueError as e:
            await _send_ephemeral(interaction, str(e))
            return

        payload = {
            "discord_id": str(interaction.user.id),
            "channel_id": str(interaction.channel.id) if reg_type == "channel" else None,
            "server_id": str(interaction.guild.id) if reg_type == "server" else None,
        }

        logger.info(
            "Registration request: url=%s type=%s entity=%s user=%s",
            url,
            reg_type,
            entity,
            interaction.user.id,
        )

        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.post(url, json=payload) as resp:
                    text = await resp.text()
                    if resp.ok:
                        await _send_ephemeral(
                            interaction,
                            f"Successfully registered this {reg_type} for {entity}.",
                        )
                        return
                    user_msg = _parse_error_body(text, resp.status)
                    logger.warning(
                        "Registration failed: status=%s url=%s body=%s",
                        resp.status,
                        url,
                        text[:500],
                    )
                    await _send_ephemeral(interaction, user_msg)
                    if Config.BUGSNAG_API_KEY and (
                        resp.status >= 500 or resp.status == 404
                    ):
                        bugsnag.notify(
                            Exception(f"Registration HTTP {resp.status} for {url}"),
                            context="register HTTP error",
                            meta_data={
                                "response": {"status": resp.status, "body": text[:2000]},
                                "request": {"url": url, "payload_keys": list(payload.keys())},
                            },
                        )
        except aiohttp.ClientError as e:
            logger.error("Registration network error: %s", e, exc_info=True)
            if Config.BUGSNAG_API_KEY:
                bugsnag.notify(
                    e,
                    context="register network error",
                    meta_data={"request": {"url": url}},
                )
            await _send_ephemeral(
                interaction,
                "Could not reach the SC Market server. Please try again in a few minutes.",
            )
        except TimeoutError:
            logger.error("Registration timed out for url=%s", url, exc_info=True)
            if Config.BUGSNAG_API_KEY:
                bugsnag.notify(
                    Exception("Registration request timed out"),
                    context="register timeout",
                    meta_data={"request": {"url": url}},
                )
            await _send_ephemeral(
                interaction,
                "The registration request timed out. Please try again.",
            )
        except Exception as e:
            logger.error("Unexpected registration error: %s", e, exc_info=True)
            if Config.BUGSNAG_API_KEY:
                bugsnag.notify(
                    e,
                    context="register unexpected error",
                    meta_data={
                        "request": {"url": url},
                        "traceback": traceback.format_exc(),
                    },
                )
            await _send_ephemeral(
                interaction,
                "An unexpected error occurred. Please try again or contact support.",
            )
