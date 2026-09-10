"""
/help — a self-maintaining command directory.

Walks the live application-command tree, so every command a cog registers shows
up here automatically with whatever `description=`/`describe(...)` it declares.
Add a new command and it appears in /help with no changes to this file.
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


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _top_commands(self):
        return sorted(self.bot.tree.get_commands(), key=lambda c: c.name)

    @app_commands.command(
        name="help",
        description="List the SC Market bot's commands and what each one does",
    )
    @app_commands.describe(
        command="Optional: a command or group to see details for, e.g. subscribe",
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

    def _overview_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="SC Market Bot — Commands",
            description="What each command does. Use `/help <command>` for parameters and details.",
            color=EMBED_COLOR,
        )
        for cmd in self._top_commands():
            if len(embed.fields) >= MAX_FIELDS:
                embed.set_footer(text="More commands available — use /help <command>.")
                break
            if isinstance(cmd, app_commands.Group):
                subs = sorted(cmd.commands, key=lambda c: c.name)
                value = "\n".join(
                    f"`/{cmd.name} {s.name}` — {_describe(s)}" for s in subs
                ) or "(no subcommands)"
            else:
                value = f"`/{cmd.name}` — {_describe(cmd)}"
            embed.add_field(name=f"/{cmd.name}", value=value[:1024], inline=False)
        return embed

    def _detail_embed(self, name: str) -> discord.Embed:
        for cmd in self._top_commands():
            if cmd.name != name:
                continue
            embed = discord.Embed(
                title=f"/{cmd.name}",
                description=_describe(cmd),
                color=EMBED_COLOR,
            )
            if isinstance(cmd, app_commands.Group):
                for sub in sorted(cmd.commands, key=lambda c: c.name):
                    body = _describe(sub)
                    params = _params(sub)
                    if params:
                        body += "\n" + params
                    embed.add_field(name=f"/{cmd.name} {sub.name}", value=body[:1024], inline=False)
            else:
                params = _params(cmd)
                if params:
                    embed.add_field(name="Parameters", value=params[:1024], inline=False)
            return embed
        return discord.Embed(
            title="Command not found",
            description=f"No command named `{name}`. Run `/help` to see them all.",
            color=NOT_FOUND_COLOR,
        )
