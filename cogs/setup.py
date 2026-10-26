"""/setup — one guided command for every way SC Market can talk to a channel.

It does not add new behaviour: it calls the same backend routes as
/register channel and /subscribe alerts, but asks one question ("what should
this channel get?"), checks the right Discord permission for that answer, and
explains what will happen next.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.registration import register
from cogs.subscribe import create_alert_subscription
from util.checks import guild_permissions_failure
from util.errors import describe_error, send_ephemeral
from util.owners import org_autocomplete

logger = logging.getLogger("SCMarketBot.SetupCog")

SITE = "https://sc-market.space"

THREADS = "threads"
ALERTS = "alerts"
WEBHOOK = "webhook"

KIND_CHOICES = [
    app_commands.Choice(name="Order threads: a private thread with the buyer for each order", value=THREADS),
    app_commands.Choice(name="Alerts: a post for each new order or offer, with a Claim button", value=ALERTS),
    app_commands.Choice(name="Webhook: order event messages, configured on the website", value=WEBHOOK),
]

# The Discord permission the member needs for each kind (same as the commands
# /setup stands in for: /register needs Administrator, /subscribe Manage Channels).
REQUIRED_PERMISSIONS = {
    THREADS: {"administrator": True},
    ALERTS: {"manage_channels": True},
    WEBHOOK: {},
}


def webhook_embed(org) -> discord.Embed:
    shop = "your org's shop" if org else "your shop"
    perm = " (needs the org's Manage Webhooks permission)" if org else ""
    embed = discord.Embed(
        title="Set up a webhook",
        description=(
            "A webhook posts a message for the shop events you pick: order created, order assigned, "
            "status change, review, comment, and market bid. It has no Claim button and opens no buyer threads."
        ),
        color=0x2196F3,
        url=SITE,
    )
    embed.add_field(
        name="Steps",
        value=(
            "1. In Discord, open this channel's settings › **Integrations** › **Webhooks** › **New Webhook**, "
            "then **Copy Webhook URL** (needs Manage Webhooks in this server).\n"
            f"2. On sc-market.space, open {shop}'s **Settings** and find the **Webhooks** section{perm}.\n"
            "3. Paste the URL, pick the events, and save."
        ),
        inline=False,
    )
    return embed


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Set up SC Market in this channel: order threads, order alerts, or a webhook",
    )
    @app_commands.describe(
        kind="What this channel should get; see /help alerts to compare them",
        org="Your org's Spectrum ID, e.g. SCMARKET; leave empty to set it up for yourself",
    )
    @app_commands.choices(kind=KIND_CHOICES)
    async def setup(
        self,
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        org: str = None,
    ):
        org = (org or "").strip() or None
        logger.info("Setup requested: kind=%s org=%s guild=%s", kind.value, bool(org), interaction.guild_id)

        if kind.value == WEBHOOK:
            await send_ephemeral(interaction, embed=webhook_embed(org))
            return

        failure = guild_permissions_failure(interaction, **REQUIRED_PERMISSIONS[kind.value])
        if failure:
            await send_ephemeral(interaction, describe_error(interaction, failure))
            return

        await interaction.response.defer(ephemeral=True)
        if kind.value == THREADS:
            await register(interaction, "channel", "contractor" if org else "user", org or "")
        else:
            await create_alert_subscription(interaction, org)

    @setup.autocomplete("org")
    async def setup_org_autocomplete(self, interaction: discord.Interaction, current: str):
        return await org_autocomplete(self.bot, interaction, current)
