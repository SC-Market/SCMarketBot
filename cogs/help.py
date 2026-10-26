"""
/help — a self-maintaining command directory, plus the 3-step setup guide.

Walks the live application-command tree, so every command a cog registers shows
up here automatically with whatever `description=`/`describe(...)` it declares.
Add a new command and it appears in /help with no changes to this file (it is
filed under "Other" until it is given an area in AREAS).
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("SCMarketBot.HelpCog")

EMBED_COLOR = 0x2196F3
NOT_FOUND_COLOR = 0xF44336
# Discord allows at most 25 fields per embed; keep headroom.
MAX_FIELDS = 24

BOT_INVITE = (
    "https://discord.com/oauth2/authorize?client_id=868709691469987860"
    "&permissions=361314126849&integration_type=0&scope=bot"
)

# Staff-only commands; hidden from the directory (they refuse everyone else).
HIDDEN = {"admin"}

# Top-level command -> area, in the order the areas are shown.
AREAS = {
    "Set up": ["setup", "help"],
    "Orders": ["order"],
    "Sell": ["listing"],
    "Buy and browse": ["search", "watchlist"],
    "Crafting": ["blueprint"],
}

ALERTS_TOPIC = "alerts"

SETUP_STEPS = (
    "**Get started in 3 steps**\n"
    "1. **Link your Discord** on sc-market.space (Settings). The bot knows you by your Discord account.\n"
    f"2. **[Add the bot]({BOT_INVITE})** to your server.\n"
    "3. **In the channel you want to use, run `/setup threads` or `/setup alerts`** "
    "(or `/setup webhook` for the website's webhook steps). For an org, fill in `org` with its Spectrum ID.\n"
    "-# Not sure which? `/help alerts` compares them. `/setup status` shows what a channel gets."
)


def _describe(cmd) -> str:
    return (getattr(cmd, "description", None) or "No description").strip()


def _params(cmd) -> str:
    params = getattr(cmd, "parameters", None) or []
    lines = []
    for p in params:
        req = " (required)" if getattr(p, "required", False) else ""
        hint = (getattr(p, "description", None) or "").strip()
        lines.append(f"• `{p.name}`{req}{' — ' + hint if hint else ''}")
    return "\n".join(lines)


def _command_lines(cmd) -> str:
    if isinstance(cmd, app_commands.Group):
        lines = []
        for sub in sorted(cmd.commands, key=lambda c: c.name):
            if isinstance(sub, app_commands.Group):
                lines += [f"`/{cmd.name} {sub.name} {s.name}` — {_describe(s)}" for s in sorted(sub.commands, key=lambda c: c.name)]
            else:
                lines.append(f"`/{cmd.name} {sub.name}` — {_describe(sub)}")
        return "\n".join(lines) or "(no subcommands)"
    return f"`/{cmd.name}` — {_describe(cmd)}"


def alerts_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Order threads, alerts or webhooks?",
        description=(
            "Three ways to hear about orders in Discord. They work side by side; most org shops use "
            "threads for talking to buyers plus alerts in a staff channel."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Order threads",
        value=(
            "A private thread per order or offer, with the buyer and the assigned seller added. "
            "Messages sync with the order chat on the site, and `/order status` works inside it. "
            "Each shop, org or member has one thread channel. Set up with `/setup threads`.\n"
            "-# Needs: Manage Channels in Discord; for an org, its Manage Webhooks permission on SC Market."
        ),
        inline=False,
    )
    embed.add_field(
        name="Alerts",
        value=(
            "A post in this channel for each new unassigned org order and each new offer, with a **Claim** "
            "button that assigns it to whoever clicks (needs the org's Claim Orders permission). "
            "Personal alerts show offers sent to you, without a Claim button. Set up with `/setup alerts`.\n"
            "-# Needs: Manage Channels in Discord; for an org, its Manage Orders or Manage Webhooks permission."
        ),
        inline=False,
    )
    embed.add_field(
        name="Public contract feed",
        value=(
            "A post for each new public contract anyone opens on SC Market (title, kind, payment, cost "
            "and a link). Set up with `/setup contracts`.\n"
            "-# Needs: Manage Channels in Discord; for an org, its Manage Orders or Manage Webhooks permission."
        ),
        inline=False,
    )
    embed.add_field(
        name="Webhook",
        value=(
            "A message for the shop events you choose (order created or assigned, status change, review, "
            "bid). No buttons, no threads. Set it up in your shop's Settings on the website; "
            "`/setup webhook` shows the steps.\n"
            "-# Needs: Manage Webhooks in Discord to create the URL; for an org shop, the org's Manage Market "
            "permission on SC Market."
        ),
        inline=False,
    )
    return embed


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _top_commands(self):
        return sorted(
            (c for c in self.bot.tree.get_commands() if c.name not in HIDDEN),
            key=lambda c: c.name,
        )

    @app_commands.command(
        name="help",
        description="How to set up the SC Market bot, and what every command does",
    )
    @app_commands.describe(
        command="Optional: a command to see its options, e.g. setup, or 'alerts' to compare alert types",
    )
    async def help(self, interaction: discord.Interaction, command: str = None):
        await interaction.response.defer(ephemeral=True)
        try:
            if command:
                embed = self._detail_embed(command.strip().lstrip("/"))
            else:
                embed = self._overview_embed()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to build help: {e}")
            await interaction.followup.send(
                "❌ Couldn't build the help list. Try again shortly.", ephemeral=True
            )

    @help.autocomplete("command")
    async def help_command_autocomplete(self, interaction: discord.Interaction, current: str):
        names = [ALERTS_TOPIC] + [c.name for c in self._top_commands()]
        current = (current or "").lower().lstrip("/")
        return [app_commands.Choice(name=n, value=n) for n in names if current in n][:25]

    def _overview_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="SC Market Bot",
            description=SETUP_STEPS,
            color=EMBED_COLOR,
        )
        commands_by_name = {c.name: c for c in self._top_commands()}
        placed = set()
        sections = []
        for area, names in AREAS.items():
            cmds = [commands_by_name[n] for n in names if n in commands_by_name]
            placed.update(c.name for c in cmds)
            if cmds:
                sections.append((area, cmds))
        other = [c for n, c in commands_by_name.items() if n not in placed]
        if other:
            sections.append(("Other", other))

        for area, cmds in sections:
            if len(embed.fields) >= MAX_FIELDS:
                embed.set_footer(text="More commands available — use /help <command>.")
                break
            value = "\n".join(_command_lines(c) for c in cmds)
            if len(value) > 1024:
                value = value[:1000].rsplit("\n", 1)[0] + "\n… use `/help <command>` for the rest"
            embed.add_field(name=area, value=value, inline=False)
        embed.set_footer(text="Use /help <command> for a command's options.")
        return embed

    def _detail_embed(self, name: str) -> discord.Embed:
        if name.lower() == ALERTS_TOPIC:
            return alerts_embed()
        for cmd in self._top_commands():
            if cmd.name != name.lower():
                continue
            embed = discord.Embed(
                title=f"/{cmd.name}",
                description=_describe(cmd),
                color=EMBED_COLOR,
            )
            if isinstance(cmd, app_commands.Group):
                for sub in sorted(cmd.commands, key=lambda c: c.name):
                    subs = sorted(sub.commands, key=lambda c: c.name) if isinstance(sub, app_commands.Group) else [sub]
                    for leaf in subs:
                        if len(embed.fields) >= MAX_FIELDS:
                            break
                        body = _describe(leaf)
                        params = _params(leaf)
                        if params:
                            body += "\n" + params
                        embed.add_field(name=f"/{leaf.qualified_name}", value=body[:1024], inline=False)
            else:
                params = _params(cmd)
                if params:
                    embed.add_field(name="Options", value=params[:1024], inline=False)
            return embed
        return discord.Embed(
            title="Command not found",
            description=f"No command named `{name}`. Run `/help` to see them all.",
            color=NOT_FOUND_COLOR,
        )
