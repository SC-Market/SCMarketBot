"""/search — find listings by name, seller, category, price and quality."""
import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from util.fetch import public_fetch, search_shops
from util.listings import create_v2_search_embed, v2_item_types, v2_sorting_methods

logger = logging.getLogger("SCMarketBot.SearchCog")


class SearchResultView(discord.ui.View):
    """Paginator with Buy/Offer buttons for search results."""

    def __init__(self, listings: list, author_id: int):
        super().__init__(timeout=600)
        self.listings = listings
        self.author_id = author_id
        self.current_page = 0

    def get_embed(self):
        return create_v2_search_embed(self.listings[self.current_page])

    def get_listing(self):
        return self.listings[self.current_page]

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return
        self.current_page = (self.current_page - 1) % len(self.listings)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return
        self.current_page = (self.current_page + 1) % len(self.listings)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.green, emoji="🛒")
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.marketplace import BuyModal
        listing = self.get_listing()
        price = listing.get('price_min', 0)
        modal = BuyModal(interaction.client, listing['listing_id'], listing['title'], price)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Offer", style=discord.ButtonStyle.blurple, emoji="💬")
    async def offer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.marketplace import OfferModal
        listing = self.get_listing()
        modal = OfferModal(interaction.client, listing['listing_id'], listing['title'])
        await interaction.response.send_modal(modal)


def seller_choice(shop: dict) -> app_commands.Choice[str]:
    """A shop as a seller choice: "Shop name · org SCMARKET" -> its slug."""
    owner = shop.get("owner") or {}
    if owner.get("type") == "contractor":
        who = f"org {owner.get('slug')}"
    elif owner.get("slug"):
        who = owner["slug"]
    else:
        who = shop["slug"]
    return app_commands.Choice(name=f"{shop['name'][:70]} · {who}"[:100], value=shop["slug"])


def search_params(
    query: Optional[str],
    seller: Optional[str],
    item_type: Optional[str],
    sorting: Optional[str],
    quantity_available: int,
    min_cost: int,
    max_cost: int,
    quality_min: Optional[int],
    quality_max: Optional[int],
) -> dict:
    """Query string for GET /v2/listings/search."""
    params = {
        "sort_by": sorting or "created_at",
        "sort_order": "asc" if sorting == "price" else "desc",
        "quantity_min": quantity_available,
        "page": 1,
        "page_size": 25,
    }
    if query:
        params["text"] = query
    if seller:
        params["shop_slug"] = seller.strip().lower()
    if item_type:
        params["item_type"] = item_type
    if min_cost:
        params["price_min"] = min_cost
    if max_cost:
        params["price_max"] = max_cost
    if quality_min:
        params["quality_tier_min"] = quality_min
    if quality_max:
        params["quality_tier_max"] = quality_max
    return params


class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="search",
        description="Search SC Market listings by name or seller, with category, price and quality filters",
    )
    @app_commands.describe(
        query="Item or service to search for, e.g. Medical Supplies; optional when you pick a seller",
        seller="Only this seller's listings: pick a user's or org's shop from the list",
        item_type="Category to filter by, e.g. Armor",
        sorting="Order to sort results by, e.g. Price: Low to High",
        quantity_available="Minimum quantity in stock, e.g. 10",
        min_cost="Minimum price in aUEC, e.g. 1000",
        max_cost="Maximum price in aUEC, e.g. 50000",
        quality_min="Minimum quality tier from 1 to 5, e.g. 2",
        quality_max="Maximum quality tier from 1 to 5, e.g. 5",
    )
    @app_commands.choices(
        item_type=[app_commands.Choice(name=item.capitalize(), value=item) for item in v2_item_types],
        sorting=[app_commands.Choice(name=value, value=key) for key, value in v2_sorting_methods.items()],
    )
    async def search(
        self,
        interaction: discord.Interaction,
        query: str = None,
        seller: str = None,
        item_type: app_commands.Choice[str] = None,
        sorting: app_commands.Choice[str] = None,
        quantity_available: int = 1,
        min_cost: int = 0,
        max_cost: int = 0,
        quality_min: int = None,
        quality_max: int = None,
    ):
        query = (query or "").strip() or None
        seller = (seller or "").strip() or None
        if not query and not seller:
            await interaction.response.send_message(
                "❌ Enter something to search for in `query`, or pick a seller in `seller`.", ephemeral=True
            )
            return

        await interaction.response.defer()
        params = search_params(
            query,
            seller,
            item_type.value if item_type else None,
            sorting.value if sorting else None,
            quantity_available,
            min_cost,
            max_cost,
            quality_min,
            quality_max,
        )
        result = await public_fetch("/v2/listings/search", params=params, session=self.bot.session)

        what = f"**{query}**" if query else "this seller"
        if seller and query:
            what += " from this seller"
        listings = result.get("listings", []) if isinstance(result, dict) else []
        if not listings:
            hint = " Pick the seller from the suggestions list." if seller else " Try a shorter search or fewer filters."
            await interaction.followup.send(f"No listings found for {what}.{hint}")
            return

        active_listings = [item for item in listings if item.get("quantity_available", 0) > 0]
        if not active_listings:
            await interaction.followup.send(
                f"No listings for {what} are in stock right now. Try `/watchlist add` to get a DM when one is."
            )
            return

        view = SearchResultView(active_listings, interaction.user.id)
        await interaction.followup.send(embed=view.get_embed(), view=view)

    @search.autocomplete("seller")
    async def seller_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            shops = await search_shops(current, session=self.bot.session)
        except Exception as e:
            logger.error(f"Seller autocomplete failed: {e}")
            return []
        return [seller_choice(shop) for shop in shops][:25]
