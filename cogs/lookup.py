import datetime

import aiohttp
import discord
import humanize
from discord import app_commands
from discord.ext import commands
from discord.ext.paginators.button_paginator import ButtonPaginator

from util.fetch import public_fetch
from util.listings import create_market_embed, categories, sorting_methods, sale_types, create_market_embed_individual


class Lookup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="search")
    @app_commands.describe(
        query='The search query',
        category='What category the item belongs to',
        sorting='What order to sort the listings by',
        sale_type='The method of sale',
        quantity_available='The minimum quantity available an item must have',
        min_cost='The minimum cost of items to search',
        max_cost='The maximum cost of items to search',
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name=item, value=item.lower()) for item in categories
        ],
        sorting=[
            app_commands.Choice(name=value, value=key) for key, value in sorting_methods.items()
        ],
        sale_type=[
            app_commands.Choice(name=item, value=item.lower()) for item in sale_types
        ],
    )
    async def search(
            self,
            interaction: discord.Interaction,
            query: str,
            category: app_commands.Choice[str] = '',
            sorting: app_commands.Choice[str] = 'activity',
            sale_type: app_commands.Choice[str] = '',
            quantity_available: int = 1,
            min_cost: int = 0,
            max_cost: int = 0,
    ):
        """Search the site market listings"""
        params = {
            'query': query,
            'sort': sorting,
            'quantityAvailable': quantity_available,
            'minCost': min_cost,
            'page_size': 48,
            'index': 0
        }

        if category:
            params['item_type'] = category
        if sale_type:
            params['sale_type'] = sale_type
        if max_cost:
            params['maxCost'] = max_cost

        result = await public_fetch(
            "/market/public/search",
            params=params,
            session=self.bot.session,
        )

        embeds = [create_market_embed(item) for item in result['listings'] if item['listing']['quantity_available']]

        paginator = ButtonPaginator(embeds, author_id=interaction.user.id)
        await paginator.send(interaction)

    lookup = app_commands.Group(name="lookup", description="Look up an org or user's market listings")

    @lookup.command(name="user")
    @app_commands.describe(
        handle='The handle of the user',
    )
    async def user_search(
            self,
            interaction: discord.Interaction,
            handle: str,
    ):
        """Lookup the market listings for a user"""
        try:
            result = await public_fetch(
                f"/market/user/{handle}",
                session=self.bot.session,
            )
        except:
            await interaction.response.send_message("Invalid user")
            return

        if not result:
            await interaction.response.send_message("No listings to display for user")
            return

        embeds = [create_market_embed_individual(item) for item in result]

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
    ):
        """Lookup the market listings for an org"""
        try:
            result = await public_fetch(
                f"/market/contractor/{spectrum_id}",
                session=self.bot.session,
            )
        except:
            await interaction.response.send_message("Invalid org")
            return

        if not result:
            await interaction.response.send_message("No listings to display for org")
            return

        embeds = [create_market_embed_individual(item) for item in result if item['listing']['quantity_available']]

        paginator = ButtonPaginator(embeds, author_id=interaction.user.id)
        await paginator.send(interaction)