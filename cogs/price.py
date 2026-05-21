import json
import logging
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post, get_user_listings, get_user_orgs, get_org_listings

logger = logging.getLogger('SCMarketBot.PriceCog')


class Price(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="price")
    @app_commands.describe(
        owner='The owner of the listing. Either you or one of your contractors',
        listing='The listing to reprice',
        new_price='The new price in aUEC',
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
            await interaction.response.send_message("Price must be greater than 0.", ephemeral=True)
            return

        try:
            listing_payload = json.loads(listing)
        except json.JSONDecodeError:
            await interaction.response.send_message("Invalid listing format. Please try again.", ephemeral=True)
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
            await interaction.response.send_message(f"Failed to update price: {response['error']}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Price for [{listing_payload['t']}](<https://sc-market.space/market/{listing_id}>) "
                f"updated from `{old_price:,}` to `{new_price:,}` aUEC."
            )

    @set_price.autocomplete('listing')
    async def price_listing_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            if interaction.namespace.owner != "_ME":
                try:
                    owner = json.loads(interaction.namespace.owner)
                    listings = await get_org_listings(owner['s'], interaction.user.id, session=self.bot.session)
                except json.JSONDecodeError:
                    return []
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
        try:
            orgs = await get_user_orgs(interaction.user.id, session=self.bot.session)
            choices = [
                app_commands.Choice(
                    name=f"{org['name']} ({org['spectrum_id']})",
                    value=json.dumps(dict(s=org['spectrum_id'], n=org['name']))
                )
                for org in orgs if
                current.lower() in org['name'].lower() or current.lower() in org['spectrum_id'].lower()
            ][:24] + [app_commands.Choice(name="Me", value='_ME')]
            return choices
        except Exception as e:
            logger.error(f"Error in price owner autocomplete: {e}")
            return [app_commands.Choice(name="Me", value='_ME')]
