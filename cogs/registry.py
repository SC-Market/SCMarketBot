"""Every cog the bot loads, in one list, so main.py and the tests agree."""
from cogs.admin import Admin
from cogs.blueprint import Blueprint
from cogs.claims import Claims
from cogs.help import Help
from cogs.listing import Listing
from cogs.order import order
from cogs.search import Search
from cogs.setup import Setup
from cogs.watchlist import Watchlist

COGS = [
    Setup,
    Claims,
    order,
    Listing,
    Search,
    Watchlist,
    Blueprint,
    Help,
    Admin,
]


async def add_cogs(bot) -> None:
    for cog in COGS:
        await bot.add_cog(cog(bot))
