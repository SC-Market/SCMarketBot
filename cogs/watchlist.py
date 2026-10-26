import logging

import discord
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post, internal_fetch

logger = logging.getLogger('SCMarketBot.WatchlistCog')


class Watchlist(commands.GroupCog, group_name="watchlist", group_description="Get a DM when an item you want is listed at or below your price"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="Watch an item: get a DM when it's listed at or below your target price")
    @app_commands.describe(
        query='Item name to watch for, e.g. Medical Supplies',
        max_price='Your target price in aUEC; you get a DM at or below it, e.g. 25000',
    )
    async def watchlist_add(
            self,
            interaction: discord.Interaction,
            query: str,
            max_price: int,
    ):
        """Add an item to your watchlist with a price alert"""
        if max_price <= 0:
            await interaction.response.send_message("❌ The target price must be greater than 0 aUEC.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        response = await internal_post(
            "/threads/watchlist/add",
            json={
                "discord_id": str(interaction.user.id),
                "query": query,
                "max_price": max_price,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't add it to your watchlist: {response['error']}", ephemeral=True)
        else:
            embed = discord.Embed(
                title="Watchlist Updated",
                description=f"You'll be notified when **{query}** is listed at or below **{max_price:,} aUEC**.",
                color=0x10b881,
            )
            embed.add_field(
                name="What's next",
                value="From now on you'll get a DM whenever a matching listing drops to your target "
                      "price or comes back in stock.\n"
                      "-# Stop alerts with /watchlist remove · see everything you watch with /watchlist list",
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="remove", description="Stop watching an item, so you get no more DMs for it")
    @app_commands.describe(
        item='Watchlist item to remove; pick from the list, e.g. Medical Supplies (≤ 25,000 aUEC)',
    )
    async def watchlist_remove(
            self,
            interaction: discord.Interaction,
            item: str,
    ):
        """Remove an item from your watchlist"""
        await interaction.response.defer(ephemeral=True)

        response = await internal_post(
            "/threads/watchlist/remove",
            json={
                "discord_id": str(interaction.user.id),
                "watchlist_id": item,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't remove it: {response['error']}", ephemeral=True)
        else:
            await interaction.followup.send(
                "Removed from your watchlist. You'll no longer get price or stock alerts for this item.\n"
                "-# Watch it again with /watchlist add · see what's left with /watchlist list",
                ephemeral=True,
            )

    @app_commands.command(name="list", description="Show the items you watch and their target prices")
    async def watchlist_list(self, interaction: discord.Interaction):
        """View your current watchlist"""
        await interaction.response.defer(ephemeral=True)

        response = await internal_fetch(
            f"/threads/watchlist/{interaction.user.id}",
            session=self.bot.session,
        )

        items = response.get("items", [])
        if not items:
            await interaction.followup.send("Your watchlist is empty. Use `/watchlist add` to start watching items.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Your Watchlist",
            color=0x5865F2,
        )

        for item in items[:25]:
            current_price_text = ""
            if item.get("current_lowest"):
                current_price_text = f" (current: {item['current_lowest']:,} aUEC)"
            embed.add_field(
                name=f"{item['query']}",
                value=f"Alert when ≤ **{item['max_price']:,} aUEC**{current_price_text}\nID: `{item['id']}`",
                inline=False,
            )

        embed.set_footer(text=f"{len(items)} item(s) watched")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @watchlist_remove.autocomplete('item')
    async def watchlist_item_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ):
        try:
            response = await internal_fetch(
                f"/threads/watchlist/{interaction.user.id}",
                session=self.bot.session,
            )
            items = response.get("items", [])
            return [
                app_commands.Choice(
                    name=f"{item['query']} (≤ {item['max_price']:,} aUEC)",
                    value=item['id'],
                )
                for item in items
                if current.lower() in item['query'].lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in watchlist autocomplete: {e}")
            return []
