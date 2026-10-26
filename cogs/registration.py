import json
import logging
from urllib.parse import quote

import aiohttp
import bugsnag
import discord
from discord import app_commands
from discord.ext import commands

from util.checks import guild_administrator
from util.config import Config
from util.errors import send_ephemeral
from util.owners import org_autocomplete

logger = logging.getLogger("SCMarketBot.registration")

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

ORG_NAME_HELP = "Your org's Spectrum ID; pick from the list, e.g. SCMARKET"


def _registration_endpoint(entity: str, name: str) -> str:
    base = Config.discord_backend_base().rstrip("/")
    if entity == "user":
        return f"{base}/register/user"
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValueError("❌ Enter your org's Spectrum ID, e.g. SCMARKET.")
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


def registration_payload(interaction, reg_type: str) -> dict:
    """Body for POST /register/*.

    A thread channel only works inside the official server (thread creation
    looks the channel up in that guild), so registering a channel also makes
    its server the official one. Registering just the server leaves the
    channel alone.
    """
    return {
        "discord_id": str(interaction.user.id),
        "channel_id": str(interaction.channel.id) if reg_type == "channel" else None,
        "server_id": str(interaction.guild.id),
    }


# What the bot itself needs in a thread channel (forum channels open posts,
# so they need Send Messages instead of Create Private Threads).
THREAD_CHANNEL_PERMS = ("view_channel", "create_private_threads", "send_messages_in_threads", "create_instant_invite")
FORUM_CHANNEL_PERMS = ("view_channel", "send_messages", "send_messages_in_threads", "create_instant_invite")


def missing_bot_permissions(app_permissions, channel_type) -> list:
    """Bot permissions this channel lacks for order threads, as display names."""
    if app_permissions is None:
        return []
    is_forum = getattr(channel_type, "name", str(channel_type)) == "forum"
    needed = FORUM_CHANNEL_PERMS if is_forum else THREAD_CHANNEL_PERMS
    return [
        name.replace("_", " ").title().replace("Instant Invite", "Invite")
        for name in needed
        if not getattr(app_permissions, name, False)
    ]


def success_message(reg_type: str, entity: str, name: str) -> str:
    target = f"the org **{name}**" if entity == "contractor" else "you"
    if reg_type == "channel":
        unlocked = (
            f"New orders and offers for {target} will now open a private thread in this channel, "
            "with the buyer and the assigned seller added, and this server is now the one buyers are invited to."
        )
        bot_needs = (
            "-# The bot needs View Channel, Create Private Threads and Send Messages in Threads here. "
            "Forum channels work too."
        )
    else:
        unlocked = (
            f"This server is now where buyers of {target} are invited to talk with the seller. "
            "Run `/register channel` (or `/setup`) in the channel that should hold the order threads."
        )
        bot_needs = "-# The bot needs Create Invite in this server."
    alerts = (
        f"/subscribe alerts {name}" if entity == "contractor" else "/subscribe alerts_user"
    )
    return (
        f"✅ Registered this {reg_type} for {target}.\n"
        f"{unlocked}\n"
        f"{bot_needs}\n"
        f"-# Also want a post with a Claim button for each new order? Run {alerts} in a staff channel."
    )


async def register(
    interaction: discord.Interaction,
    reg_type: str,
    entity: str,
    name: str = "",
) -> bool:
    """Register this channel or server for order threads. Returns True on success."""
    if not interaction.response.is_done():
        # The backend call can take longer than Discord's 3 second reply window.
        await interaction.response.defer(ephemeral=True)
    try:
        url = _registration_endpoint(entity, name)
    except ValueError as e:
        await send_ephemeral(interaction, str(e))
        return False

    payload = registration_payload(interaction, reg_type)

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
                    message = success_message(reg_type, entity, name)
                    if reg_type == "channel":
                        missing = missing_bot_permissions(
                            getattr(interaction, "app_permissions", None),
                            getattr(interaction.channel, "type", None),
                        )
                        if missing:
                            message += (
                                "\n⚠️ The bot is missing **" + "**, **".join(missing) + "** in this channel, "
                                "so threads will fail until a server admin grants them in the channel's Permissions."
                            )
                    await send_ephemeral(interaction, message)
                    return True
                user_msg = _parse_error_body(text, resp.status)
                logger.warning(
                    "Registration failed: status=%s url=%s body=%s",
                    resp.status,
                    url,
                    text[:500],
                )
                await send_ephemeral(interaction, f"❌ {user_msg}")
                if Config.BUGSNAG_API_KEY and (resp.status >= 500 or resp.status == 404):
                    bugsnag.notify(
                        Exception(f"Registration HTTP {resp.status} for {url}"),
                        context="register HTTP error",
                        meta_data={
                            "response": {"status": resp.status, "body": text[:2000]},
                            "request": {"url": url, "payload_keys": list(payload.keys())},
                        },
                    )
                return False
    except aiohttp.ClientError as e:
        logger.error("Registration network error: %s", e, exc_info=True)
        await send_ephemeral(
            interaction,
            "❌ Could not reach the SC Market server. Please try again in a few minutes.",
        )
    except TimeoutError:
        logger.error("Registration timed out for url=%s", url, exc_info=True)
        await send_ephemeral(interaction, "❌ The registration request timed out. Please try again.")
    return False


class Registration(
    commands.GroupCog,
    name="register",
    group_description="Connect this server or channel for order-fulfillment threads (needs Administrator)",
):
    """Connect this server or channel for order-fulfillment threads."""

    channel = app_commands.Group(
        name="channel",
        description="Open a private thread in this channel for each new order (needs Administrator)",
    )
    server = app_commands.Group(
        name="server",
        description="Make this the server buyers are invited to for their orders (needs Administrator)",
    )

    def __init__(self, bot=None):
        self.bot = bot
        super().__init__()

    @channel.command(
        name="contractor",
        description="Open a private thread here for each new order of your org",
    )
    @guild_administrator()
    @app_commands.describe(name=ORG_NAME_HELP)
    async def contractor_channel(self, interaction: discord.Interaction, name: str):
        """Register a channel as the channel that will house threads for order fulfillment for your contractor. Make sure the bot has permission to see the channel and make private threads there."""
        await register(interaction, "channel", "contractor", name)

    @channel.command(
        name="user",
        description="Open a private thread here for each new order placed with you",
    )
    @guild_administrator()
    async def user_channel(self, interaction: discord.Interaction):
        """Register a channel as the channel that will house threads for order fulfillment for your user. Make sure the bot has permission to see the channel and make private threads there."""
        await register(interaction, "channel", "user")

    @server.command(
        name="contractor",
        description="Invite your org's buyers to this server to talk about their orders",
    )
    @guild_administrator()
    @app_commands.describe(name=ORG_NAME_HELP)
    async def contractor_server(self, interaction: discord.Interaction, name: str):
        """Register a server as the official server for order fulfillment for your contractor."""
        await register(interaction, "server", "contractor", name)

    @server.command(
        name="user",
        description="Invite your buyers to this server to talk about their orders",
    )
    @guild_administrator()
    async def user_server(self, interaction: discord.Interaction):
        """Register a server as the official server for order fulfillment for your user."""
        await register(interaction, "server", "user")

    @contractor_channel.autocomplete("name")
    @contractor_server.autocomplete("name")
    async def contractor_name_autocomplete(self, interaction: discord.Interaction, current: str):
        return await org_autocomplete(self.bot, interaction, current)
