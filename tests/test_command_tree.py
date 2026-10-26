"""The whole slash-command surface, as Discord will see it after tree.sync().

Guards the non-breaking promise (every existing command keeps its name) and
the self-documenting promise (every command and option explains itself).
"""
import discord
import pytest
import pytest_asyncio
from discord import app_commands
from discord.ext import commands

from cogs import help as help_module
from cogs.registry import add_cogs

# Every command that existed before the simplification; renaming or removing
# any of these would break servers and muscle memory, so it needs an owner decision.
EXISTING = {
    "admin admin_info", "admin health", "admin queue_status", "admin restart_sqs",
    "blueprint conversion", "blueprint inventory", "blueprint own", "blueprint search", "blueprint unown",
    "help", "import uex", "list", "lookup org", "lookup user", "order status", "price",
    "register channel contractor", "register channel user", "register server contractor", "register server user",
    "search", "stock add", "stock set", "stock sub", "stock view",
    "subscribe alerts", "subscribe alerts_user", "unsubscribe alerts",
    "watchlist add", "watchlist list", "watchlist remove",
}
NEW = {"setup"}


@pytest_asyncio.fixture
async def bot():
    b = commands.Bot(command_prefix="/", intents=discord.Intents.none())
    await add_cogs(b)
    yield b


def _walk(cmds):
    for cmd in cmds:
        yield cmd
        if isinstance(cmd, app_commands.Group):
            yield from _walk(cmd.commands)


def _leaves(bot):
    return [c for c in _walk(bot.tree.get_commands()) if not isinstance(c, app_commands.Group)]


@pytest.mark.asyncio
async def test_existing_command_names_are_unchanged(bot):
    names = {c.qualified_name for c in _leaves(bot)}
    assert EXISTING <= names, f"missing: {EXISTING - names}"
    assert names == EXISTING | NEW


@pytest.mark.asyncio
async def test_every_command_and_group_has_a_description(bot):
    for cmd in _walk(bot.tree.get_commands()):
        assert cmd.description and cmd.description != "…", cmd.qualified_name
        assert len(cmd.description) <= 100, cmd.qualified_name


@pytest.mark.asyncio
async def test_every_option_has_help_text(bot):
    for cmd in _leaves(bot):
        for param in cmd.parameters:
            assert param.description and param.description != "…", f"{cmd.qualified_name} {param.name}"
            assert len(param.description) <= 100, f"{cmd.qualified_name} {param.name}"


@pytest.mark.asyncio
async def test_every_command_is_filed_under_a_help_area(bot):
    filed = {n for names in help_module.AREAS.values() for n in names} | help_module.HIDDEN
    top = {c.name for c in bot.tree.get_commands()}
    assert top <= filed, f"add to help.AREAS: {top - filed}"


@pytest.mark.asyncio
async def test_help_overview_fits_discord_limits_and_starts_with_setup(bot):
    embed = help_module.Help(bot)._overview_embed()
    assert len(embed) <= 6000
    assert len(embed.fields) <= 25
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert "Get started in 3 steps" in embed.description
    assert "/setup" in embed.description
    text = "\n".join(f.value for f in embed.fields)
    assert "/admin" not in text  # staff-only, hidden
    assert "`/setup`" in text and "`/register channel contractor`" in text


@pytest.mark.asyncio
async def test_help_alerts_topic_compares_the_three_mechanisms(bot):
    embed = help_module.Help(bot)._detail_embed("alerts")
    assert [f.name for f in embed.fields] == ["Order threads", "Alerts", "Webhook"]
    assert len(embed) <= 6000


@pytest.mark.asyncio
async def test_help_detail_lists_nested_subcommands(bot):
    embed = help_module.Help(bot)._detail_embed("register")
    assert {f.name for f in embed.fields} == {
        "/register channel contractor", "/register channel user",
        "/register server contractor", "/register server user",
    }


@pytest.mark.asyncio
async def test_help_autocomplete_offers_topics(bot):
    cog = help_module.Help(bot)
    choices = await cog.help_command_autocomplete(None, "al")
    assert [c.value for c in choices] == ["alerts"]
