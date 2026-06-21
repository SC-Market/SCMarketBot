from typing import List

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.paginators.button_paginator import ButtonPaginator

from util.fetch import public_fetch, search_users, search_orgs
from util.listings import (
    create_v2_search_embed,
    v2_sorting_methods,
    v2_item_types,
    display_listings_compact,
)


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


class Lookup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="search")
    @app_commands.describe(
        query='The search query',
        item_type='What category the item belongs to',
        sorting='What order to sort the listings by',
        quantity_available='The minimum quantity available',
        min_cost='The minimum cost of items to search',
        max_cost='The maximum cost of items to search',
        quality_min='Minimum quality tier (1-5)',
        quality_max='Maximum quality tier (1-5)',
    )
    @app_commands.choices(
        item_type=[
            app_commands.Choice(name=item.capitalize(), value=item) for item in v2_item_types
        ],
        sorting=[
            app_commands.Choice(name=value, value=key) for key, value in v2_sorting_methods.items()
        ],
    )
    async def search(
            self,
            interaction: discord.Interaction,
            query: str,
            item_type: app_commands.Choice[str] = None,
            sorting: app_commands.Choice[str] = None,
            quantity_available: int = 1,
            min_cost: int = 0,
            max_cost: int = 0,
            quality_min: int = None,
            quality_max: int = None,
    ):
        """Search the SC Market listings"""
        await interaction.response.defer()

        params = {
            'text': query,
            'sort_by': sorting.value if sorting else 'created_at',
            'sort_order': 'desc' if not sorting or sorting.value != 'price' else 'asc',
            'quantity_min': quantity_available,
            'page': 1,
            'page_size': 25,
        }

        if item_type:
            params['item_type'] = item_type.value
        if min_cost:
            params['price_min'] = min_cost
        if max_cost:
            params['price_max'] = max_cost
        if quality_min:
            params['quality_tier_min'] = quality_min
        if quality_max:
            params['quality_tier_max'] = quality_max

        result = await public_fetch(
            "/v2/listings/search",
            params=params,
            session=self.bot.session,
        )

        listings = result.get('listings', [])
        if not listings:
            await interaction.followup.send("No results found")
            return

        active_listings = [item for item in listings if item.get('quantity_available', 0) > 0]
        if not active_listings:
            await interaction.followup.send("No results found")
            return

        view = SearchResultView(active_listings, interaction.user.id)
        await interaction.followup.send(embed=view.get_embed(), view=view)

    lookup = app_commands.Group(name="lookup", description="Look up an org or user's market listings")

    @lookup.command(name="user")
    @app_commands.describe(
        handle='The handle of the user',
    )
    async def user_search(
            self,
            interaction: discord.Interaction,
            handle: str,
            compact: bool = False,
    ):
        """Lookup the market listings for a user"""
        await interaction.response.defer()

        try:
            # Resolve user's shop slug (convention: username-shop)
            shop_slug = f"{handle.lower()}-shop"
            result = await public_fetch(
                "/v2/listings/search",
                params={'shop_slug': shop_slug, 'page_size': 50},
                session=self.bot.session,
            )
        except Exception:
            await interaction.followup.send("Invalid user or no listings found")
            return

        listings = result.get('listings', [])
        if not listings:
            await interaction.followup.send("No listings to display for user")
            return

        if compact:
            await display_listings_compact(interaction, listings)
        else:
            embeds = [create_v2_search_embed(item) for item in listings if item.get('quantity_available', 0) > 0]
            if not embeds:
                await interaction.followup.send("No listings to display for user")
                return
            paginator = ButtonPaginator(embeds, author_id=interaction.user.id)
            await paginator.send(interaction)

    @lookup.command(name="org")
    @app_commands.describe(
        spectrum_id='The spectrum ID of the org',
    )
    async def org_search(
            self,
            interaction: discord.Interaction,
            spectrum_id: str,
            compact: bool = False,
    ):
        """Lookup the market listings for an org"""
        await interaction.response.defer()

        try:
            result = await public_fetch(
                "/v2/listings/search",
                params={'contractor_spectrum_id': spectrum_id, 'page_size': 50},
                session=self.bot.session,
            )
        except Exception:
            await interaction.followup.send("Invalid org or no listings found")
            return

        listings = result.get('listings', [])
        if not listings:
            await interaction.followup.send("No listings to display for org")
            return

        if compact:
            await display_listings_compact(interaction, listings)
        else:
            embeds = [create_v2_search_embed(item) for item in listings if item.get('quantity_available', 0) > 0]
            if not embeds:
                await interaction.followup.send("No listings to display for org")
                return
            paginator = ButtonPaginator(embeds, author_id=interaction.user.id)
            await paginator.send(interaction)

    @user_search.autocomplete('handle')
    async def autocomplete_get_users(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        users = await search_users(current, self.bot.session)
        choices = [
                      app_commands.Choice(
                          name=f"{user['display_name'][:100]} ({user['username']})",
                          value=user['username']
                      )
                      for user in users
                  ][:25]
        return choices

    @org_search.autocomplete('spectrum_id')
    async def autocomplete_get_orgs(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        orgs = await search_orgs(current, self.bot.session)

        choices = [
                      app_commands.Choice(
                          name=f"{org['name'][:30]} ({org['spectrum_id']})",
                          value=org['spectrum_id']
                      )
                      for org in orgs
                  ][:25]
        return choices
