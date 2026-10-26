"""/setup — what SC Market posts in a channel, and for whom.

- ``/setup threads [org]``: a private thread with the buyer for each new order.
- ``/setup alerts [org]``: a post for each new order and offer, with a Claim button.
- ``/setup webhook``: the steps for a shop webhook (configured on the website).
- ``/setup status``: what this channel gets.
- ``/setup remove kind [org]``: stop threads or alerts here.

Discord side: threads, alerts and remove need Manage Channels. SC Market side
(checked by the backend): an org needs Manage Webhooks for threads and Manage
Orders or Manage Webhooks for alerts; leaving ``org`` empty means yourself.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from util import channel_setups
from util.checks import guild_manage_channels, guild_only
from util.owners import org_autocomplete

logger = logging.getLogger("SCMarketBot.SetupCog")

SITE = "https://sc-market.space"
THREADS = "threads"
ALERTS = "alerts"

ORG_HELP = "Your org's Spectrum ID, e.g. SCMARKET; leave empty to set it up for yourself"
REMOVE_ORG_HELP = "The org it was set up for, e.g. SCMARKET; leave empty if it's yours"

KIND_CHOICES = [
    app_commands.Choice(name="Order threads", value=THREADS),
    app_commands.Choice(name="Order alerts", value=ALERTS),
]
KIND_LABELS = {THREADS: "order threads", ALERTS: "order alerts"}

# What the bot itself needs in a thread channel (forum channels open posts,
# so they need Send Messages instead of Create Private Threads).
THREAD_CHANNEL_PERMS = ("view_channel", "create_private_threads", "send_messages_in_threads", "create_instant_invite")
FORUM_CHANNEL_PERMS = ("view_channel", "send_messages", "send_messages_in_threads", "create_instant_invite")
ALERT_CHANNEL_PERMS = ("view_channel", "send_messages", "embed_links")


def _label(name: str) -> str:
    return name.replace("_", " ").title().replace("Instant Invite", "Invite")


def missing_bot_permissions(app_permissions, channel_type, kind: str = THREADS) -> list:
    """Bot permissions this channel lacks for ``kind``, as display names."""
    if app_permissions is None:
        return []
    if kind == ALERTS:
        needed = ALERT_CHANNEL_PERMS
    elif getattr(channel_type, "name", str(channel_type)) == "forum":
        needed = FORUM_CHANNEL_PERMS
    else:
        needed = THREAD_CHANNEL_PERMS
    return [_label(name) for name in needed if not getattr(app_permissions, name, False)]


def bot_permission_warning(interaction, kind: str) -> str:
    missing = missing_bot_permissions(
        getattr(interaction, "app_permissions", None),
        getattr(interaction.channel, "type", None),
        kind,
    )
    if not missing:
        return ""
    return (
        "\n⚠️ The bot is missing **" + "**, **".join(missing) + "** in this channel, "
        f"so {KIND_LABELS[kind]} will fail until a server admin grants them in the channel's Permissions."
    )


def clean_org(org) -> str:
    return (org or "").strip() or None


def threads_message(owner_label: str, org, moved_from) -> str:
    target = f"**{owner_label}**" if org else "you"
    lines = [
        f"✅ Order threads for {target} now open in this channel.",
        "Each new order or offer gets a private thread here with the buyer and the assigned seller. "
        "Messages sync with the order chat on the site, and `/order status` works inside the thread. "
        "Buyers who aren't in this server get an invite.",
    ]
    if moved_from:
        lines.append(f"-# They used to open in <#{moved_from['channel_id']}>; that channel no longer gets new threads.")
    lines.append("-# Forum channels work too: each order becomes a post.")
    return "\n".join(lines)


def alerts_embed(owner_label: str, org) -> discord.Embed:
    if org:
        description = (
            f"New orders and offers for **{owner_label}** will be posted here as they come in, "
            "each with a **Claim** button."
        )
        claim = (
            "Org members with the **Claim Orders** permission on SC Market can click **Claim** "
            "to take the order or offer. Orders that already have an assignee aren't posted."
        )
    else:
        description = "New offers sent to you personally will be posted here as they come in."
        claim = "Personal offers are already yours, so they have no Claim button; open the link to reply."
    embed = discord.Embed(title="✅ Order alerts are on for this channel", description=description, color=0x10B881)
    embed.add_field(name="Claiming", value=claim, inline=False)
    embed.add_field(
        name="What's next",
        value=(
            "Want a private thread with the buyer for each order too? Run `/setup threads` in the channel "
            "that should hold them.\n-# See everything this channel gets with /setup status"
        ),
        inline=False,
    )
    return embed


def webhook_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Set up a webhook",
        description=(
            "A webhook posts a message for the shop events you pick: order created, order assigned, "
            "status change, review, comment, and market bid. It has no Claim button and opens no buyer threads, "
            "and it works without the bot."
        ),
        color=0x2196F3,
        url=SITE,
    )
    embed.add_field(
        name="Steps",
        value=(
            "1. In Discord, open this channel's settings › **Integrations** › **Webhooks** › **New Webhook**, "
            "then **Copy Webhook URL** (needs Manage Webhooks in this server).\n"
            "2. On sc-market.space, open your shop's **Settings** and find the **Webhooks** section "
            "(an org shop needs the org's Manage Market permission).\n"
            "3. Paste the URL, pick the events, and save."
        ),
        inline=False,
    )
    return embed


def status_embed(setups: list) -> discord.Embed:
    """What this channel gets, one field per owner."""
    if not setups:
        return discord.Embed(
            title="Nothing is set up in this channel",
            description=(
                "Run `/setup threads` for a private thread with the buyer for each order, or "
                "`/setup alerts` for a post with a Claim button for each new order. "
                "`/help alerts` compares them."
            ),
            color=0x2196F3,
        )
    embed = discord.Embed(title="What this channel gets", color=0x2196F3)
    for s in setups[:24]:
        kinds = [KIND_LABELS[k] for k in (THREADS, ALERTS) if s.get(k)]
        if s.get("owner_type") == "shop":
            how = "-# Set on the website in the shop's Settings › Discord."
        elif s.get("owner_type") == "org":
            how = f"-# Stop with `/setup remove` and `org:{s.get('spectrum_id')}`."
        else:
            how = "-# Personal. Stop with `/setup remove`, leaving `org` empty."
        embed.add_field(
            name=f"For {s.get('owner_label')}",
            value=f"{' and '.join(kinds).capitalize()}\n{how}",
            inline=False,
        )
    return embed


class Setup(
    commands.GroupCog,
    group_name="setup",
    group_description="Choose what SC Market posts in this channel: order threads, order alerts or a webhook",
):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="threads",
        description="Open a private thread here with the buyer for each new order (needs Manage Channels)",
    )
    @app_commands.describe(org=ORG_HELP)
    @guild_manage_channels()
    async def threads(self, interaction: discord.Interaction, org: str = None):
        org = clean_org(org)
        await interaction.response.defer(ephemeral=True)
        status, body = await channel_setups.save(THREADS, interaction, org)
        if status != 200:
            await interaction.followup.send(channel_setups.error_text(status, body), ephemeral=True)
            return
        data = body.get("data") or {}
        message = threads_message(data.get("owner_label"), org, data.get("moved_from"))
        message += bot_permission_warning(interaction, THREADS)
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="alerts",
        description="Post each new order and offer here with a Claim button (needs Manage Channels)",
    )
    @app_commands.describe(org=ORG_HELP)
    @guild_manage_channels()
    async def alerts(self, interaction: discord.Interaction, org: str = None):
        org = clean_org(org)
        await interaction.response.defer(ephemeral=True)
        status, body = await channel_setups.save(ALERTS, interaction, org)
        if status != 200:
            await interaction.followup.send(channel_setups.error_text(status, body), ephemeral=True)
            return
        data = body.get("data") or {}
        warning = bot_permission_warning(interaction, ALERTS)
        await interaction.followup.send(
            warning.strip() or None, embed=alerts_embed(data.get("owner_label"), org), ephemeral=True
        )

    @app_commands.command(
        name="webhook",
        description="Show how to post shop events here with a webhook, set up on the website",
    )
    async def webhook(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=webhook_embed(), ephemeral=True)

    @app_commands.command(name="status", description="Show what SC Market sends to this channel, and for whom")
    @guild_only()
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status, body = await channel_setups.status(interaction.channel_id)
        if status != 200:
            await interaction.followup.send(channel_setups.error_text(status, body), ephemeral=True)
            return
        setups = body.get("data") or []
        embed = status_embed(setups)
        warnings = "".join(
            bot_permission_warning(interaction, kind)
            for kind in (THREADS, ALERTS)
            if any(s.get(kind) for s in setups)
        )
        await interaction.followup.send(warnings.strip() or None, embed=embed, ephemeral=True)

    @app_commands.command(
        name="remove",
        description="Stop order threads or order alerts in this channel (needs Manage Channels)",
    )
    @app_commands.describe(kind="What to stop: order threads or order alerts", org=REMOVE_ORG_HELP)
    @app_commands.choices(kind=KIND_CHOICES)
    @guild_manage_channels()
    async def remove(self, interaction: discord.Interaction, kind: app_commands.Choice[str], org: str = None):
        org = clean_org(org)
        await interaction.response.defer(ephemeral=True)
        status, body = await channel_setups.remove(kind.value, interaction, org)
        if status != 200:
            await interaction.followup.send(channel_setups.error_text(status, body), ephemeral=True)
            return
        target = f"**{(body.get('data') or {}).get('owner_label')}**" if org else "you"
        await interaction.followup.send(
            f"✅ This channel no longer gets {KIND_LABELS[kind.value]} for {target}.\n"
            "-# Turn them back on with /setup threads or /setup alerts · see what's left with /setup status",
            ephemeral=True,
        )

    @threads.autocomplete("org")
    @alerts.autocomplete("org")
    @remove.autocomplete("org")
    async def setup_org_autocomplete(self, interaction: discord.Interaction, current: str):
        return await org_autocomplete(self.bot, interaction, current)
