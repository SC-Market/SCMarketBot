"""Every cog the bot loads, in one list, so main.py and the tests agree."""
from cogs.admin import Admin
from cogs.blueprint import Blueprint
from cogs.help import Help
from cogs.listing import Listing
from cogs.lookup import Lookup
from cogs.marketplace import Marketplace
from cogs.order import order
from cogs.price import Price
from cogs.registration import Registration
from cogs.setup import Setup
from cogs.stock import stock
from cogs.subscribe import AlertSubscriptions
from cogs.watchlist import Watchlist

COGS = [
    Registration,
    Setup,
    Admin,
    Lookup,
    order,
    stock,
    AlertSubscriptions,
    Price,
    Watchlist,
    Listing,
    Marketplace,
    Blueprint,
    Help,
]


async def add_cogs(bot) -> None:
    for cog in COGS:
        await bot.add_cog(cog(bot))
