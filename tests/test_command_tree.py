"""The whole slash-command surface, as Discord will see it after tree.sync().

Pins every command by name (so a rename or removal is deliberate) and checks
that every command, group, option and choice describes what it does, within
Discord's limits.
"""
import discord
import pytest
import pytest_asyncio
from discord import app_commands
from discord.ext import commands

from cogs import help as help_module
from cogs.registry import add_cogs

COMMANDS = {
    "setup threads", "setup alerts", "setup contracts", "setup webhook", "setup status", "setup remove",
    "order status",
    "listing create", "listing price", "listing stock", "listing view", "listing import",
    "search",
    "watchlist add", "watchlist list", "watchlist remove",
    "blueprint conversion", "blueprint inventory", "blueprint own", "blueprint search", "blueprint unown",
    "help",
    "admin admin_info", "admin health", "admin queue_status", "admin restart_sqs",
}
TOP_LEVEL = {"setup", "order", "listing", "search", "watchlist", "blueprint", "help", "admin"}

# Every option, per command, so dropping or renaming one is deliberate too.
OPTIONS = {
    "setup threads": ["org"],
    "setup alerts": ["org"],
    "setup contracts": ["org"],
    "setup webhook": [],
    "setup status": [],
    "setup remove": ["kind", "org"],
    "listing create": ["owner"],
    "listing price": ["owner", "listing", "new_price"],
    "listing stock": ["owner", "listing", "mode", "quantity"],
    "listing view": ["owner"],
    "listing import": ["source", "username"],
    "search": [
        "query", "seller", "item_type", "sorting", "quantity_available",
        "min_cost", "max_cost", "quality_min", "quality_max",
    ],
}


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


def _by_name(bot):
    return {c.qualified_name: c for c in _leaves(bot)}


@pytest.mark.asyncio
async def test_the_full_command_list(bot):
    assert set(_by_name(bot)) == COMMANDS
    assert {c.name for c in bot.tree.get_commands()} == TOP_LEVEL


@pytest.mark.asyncio
async def test_options_of_the_reworked_commands(bot):
    by_name = _by_name(bot)
    for name, options in OPTIONS.items():
        assert [p.name for p in by_name[name].parameters] == options, name


@pytest.mark.asyncio
async def test_every_command_and_group_has_a_description(bot):
    for cmd in _walk(bot.tree.get_commands()):
        assert cmd.description and cmd.description != "…", cmd.qualified_name
        assert len(cmd.description) <= 100, cmd.qualified_name


@pytest.mark.asyncio
async def test_every_option_and_choice_describes_itself(bot):
    for cmd in _leaves(bot):
        for param in cmd.parameters:
            where = f"{cmd.qualified_name} {param.name}"
            assert param.description and param.description != "…", where
            assert len(param.description) <= 100, where
            for choice in param.choices:
                assert choice.name and len(choice.name) <= 100, f"{where} {choice.value}"


@pytest.mark.asyncio
async def test_no_command_names_a_removed_one(bot):
    removed = ("/register", "/subscribe", "/unsubscribe", "/lookup", "/stock", "/price", "/import", "/list ")
    texts = []
    for cmd in _walk(bot.tree.get_commands()):
        texts.append(cmd.description)
        for param in getattr(cmd, "parameters", []):
            texts.append(param.description)
    texts.append(help_module.SETUP_STEPS)
    texts += [f.value for f in help_module.alerts_embed().fields]
    for text in texts:
        assert not any(old in text for old in removed), text


@pytest.mark.asyncio
async def test_admin_is_hidden_from_members_and_dms(bot):
    admin = next(c for c in bot.tree.get_commands() if c.name == "admin")
    assert admin.default_permissions == discord.Permissions(administrator=True)
    assert admin.guild_only is True
    others = [c for c in bot.tree.get_commands() if c.name != "admin"]
    assert all(c.default_permissions is None for c in others)


@pytest.mark.asyncio
async def test_every_command_is_filed_under_a_help_area(bot):
    filed = {n for names in help_module.AREAS.values() for n in names} | help_module.HIDDEN
    top = {c.name for c in bot.tree.get_commands()}
    assert top <= filed, f"add to help.AREAS: {top - filed}"
    assert filed - help_module.HIDDEN <= top, "help.AREAS names a command that doesn't exist"


@pytest.mark.asyncio
async def test_help_overview_fits_discord_limits_and_starts_with_setup(bot):
    embed = help_module.Help(bot)._overview_embed()
    assert len(embed) <= 6000
    assert len(embed.fields) <= 25
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert "Get started in 3 steps" in embed.description
    assert "/setup threads" in embed.description and "/setup alerts" in embed.description
    text = "\n".join(f.value for f in embed.fields)
    assert "/admin" not in text  # staff-only, hidden
    for name in ("`/setup threads`", "`/setup status`", "`/listing stock`", "`/search`"):
        assert name in text


@pytest.mark.asyncio
async def test_help_alerts_topic_compares_the_mechanisms(bot):
    embed = help_module.Help(bot)._detail_embed("alerts")
    assert [f.name for f in embed.fields] == ["Order threads", "Alerts", "Public contract feed", "Webhook"]
    assert "Manage Channels" in embed.fields[0].value
    assert "/setup threads" in embed.fields[0].value and "/setup alerts" in embed.fields[1].value
    assert len(embed) <= 6000


@pytest.mark.asyncio
async def test_help_detail_lists_subcommands_with_options(bot):
    embed = help_module.Help(bot)._detail_embed("setup")
    assert {f.name for f in embed.fields} == {
        "/setup threads", "/setup alerts", "/setup contracts", "/setup webhook", "/setup status", "/setup remove",
    }
    remove = next(f for f in embed.fields if f.name == "/setup remove")
    assert "`kind` (required)" in remove.value and "`org`" in remove.value


@pytest.mark.asyncio
async def test_help_autocomplete_offers_topics(bot):
    cog = help_module.Help(bot)
    choices = await cog.help_command_autocomplete(None, "al")
    assert [c.value for c in choices] == ["alerts"]
    listing = await cog.help_command_autocomplete(None, "/listi")
    assert [c.value for c in listing] == ["listing"]


@pytest.mark.asyncio
async def test_every_command_serializes_for_sync(bot):
    # What tree.sync() sends to Discord; fails on anything Discord would reject locally.
    payload = [cmd.to_dict(bot.tree) for cmd in bot.tree.get_commands()]
    assert len(payload) == len(TOP_LEVEL)
    admin = next(p for p in payload if p["name"] == "admin")
    assert int(admin["default_member_permissions"]) == discord.Permissions(administrator=True).value
