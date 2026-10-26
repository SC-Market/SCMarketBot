import json
import logging
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post, get_user_listings, get_org_listings
from util.owners import OWNER_HELP, owner_autocomplete, parse_owner

logger = logging.getLogger('SCMarketBot.PriceCog')


class Price(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="price", description="Quickly update the price of one of your market listings")
    @app_commands.describe(
        owner=OWNER_HELP,
        listing='The listing to reprice; pick from the list, e.g. Pembroke Armor Set',
        new_price='New price in aUEC, e.g. 50000',
    )
    async def set_price(
            self,
            interaction: discord.Interaction,
            owner: str,
            listing: str,
            new_price: int,
    ):
        """Quickly update the price of a market listing"""
        if new_price <= 0:
            await interaction.response.send_message("❌ The price must be greater than 0 aUEC.", ephemeral=True)
            return

        try:
            listing_payload = json.loads(listing)
        except json.JSONDecodeError:
            await interaction.response.send_message(
                "❌ Pick the listing from the suggestions list instead of typing it.", ephemeral=True
            )
            return

        listing_id = listing_payload["l"]
        old_price = listing_payload.get("p", 0)

        payload = {
            "discord_id": str(interaction.user.id),
            "listing_id": listing_id,
            "price": new_price,
        }

        response = await internal_post(
            "/threads/market/price",
            json=payload,
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.response.send_message(f"❌ Couldn't update the price: {response['error']}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Price for [{listing_payload['t']}](<https://sc-market.space/market/{listing_id}>) "
                f"updated from `{old_price:,}` to `{new_price:,}` aUEC.\n"
                f"Buyers now see the new price on the listing.\n"
                f"-# Reprice again with /price · adjust stock with /stock set"
            )

    @set_price.autocomplete('listing')
    async def price_listing_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            spectrum_id = parse_owner(interaction.namespace.owner)
            if spectrum_id:
                listings = await get_org_listings(spectrum_id, interaction.user.id, session=self.bot.session)
            else:
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings:
                return []

            choices = [
                app_commands.Choice(
                    name=f"{listing['title'][:80]} ({int(listing.get('price', listing.get('price_min', 0))):,} aUEC)",
                    value=ujson.dumps(dict(
                        l=listing['listing_id'],
                        t=listing['title'],
                        p=int(listing.get('price', listing.get('price_min', 0)))
                    ))
                )
                for listing in listings if current.lower() in listing['title'].lower()
            ][:25]
            return choices

        except Exception as e:
            logger.error(f"Error in price listing autocomplete: {e}")
            return []

    @set_price.autocomplete('owner')
    async def price_owner_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        return await owner_autocomplete(self.bot, interaction, current)
