import json
import logging
import traceback
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.errors import send_ephemeral
from util.fetch import internal_post, get_user_listings, get_org_listings
from util.listings import display_listings_compact
from util.owners import OWNER_HELP, owner_autocomplete, parse_owner

logger = logging.getLogger('SCMarketBot.StockCog')

class stock(commands.GroupCog, group_description="Change how many of an item your listings show as available"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set", description="Set a listing's available quantity to an exact number")
    @app_commands.describe(
        owner=OWNER_HELP,
        listing='The listing to change; pick from the list, e.g. Pembroke Armor Set',
        quantity='New available quantity, e.g. 10',
    )
    async def set_stock(
            self,
            interaction: discord.Interaction,
            owner: str,
            listing: str,
            quantity: int,
    ):
        """Set the stock quantity for a given market listing"""
        await self.handle_stock_change(interaction, 'set', owner, listing, quantity)

    @app_commands.command(name="add", description="Add to a listing's available quantity (e.g. after restocking)")
    @app_commands.describe(
        owner=OWNER_HELP,
        listing='The listing to change; pick from the list, e.g. Pembroke Armor Set',
        quantity='How many to add, e.g. 5',
    )
    async def add_stock(
            self,
            interaction: discord.Interaction,
            owner: str,
            listing: str,
            quantity: int,
    ):
        """Add to the stock quantity for a given market listing"""
        await self.handle_stock_change(interaction, 'add', owner, listing, quantity)

    @app_commands.command(name="sub", description="Subtract from a listing's available quantity (e.g. after a sale off-site)")
    @app_commands.describe(
        owner=OWNER_HELP,
        listing='The listing to change; pick from the list, e.g. Pembroke Armor Set',
        quantity='How many to remove, e.g. 2',
    )
    async def sub_stock(
            self,
            interaction: discord.Interaction,
            owner: str,
            listing: str,
            quantity: int,
    ):
        """Subtract from the stock quantity for a given market listing"""
        await self.handle_stock_change(interaction, 'sub', owner, listing, quantity)

    async def handle_stock_change(self, interaction: discord.Interaction, action: str, owner: str, listing: str,
                                  quantity: int):
        """Enhanced stock change handler with comprehensive logging"""
        logger.info(f"Stock change requested: user={interaction.user.id}, action={action}, owner={owner}, quantity={quantity}")
        
        try:
            # Parse listing payload
            try:
                listing_payload = json.loads(listing)
                logger.debug(f"Parsed listing payload: {listing_payload}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse listing JSON: {e}")
                logger.error(f"Raw listing string: {listing}")
                await interaction.response.send_message(
                    "❌ Pick the listing from the suggestions list instead of typing it.", ephemeral=True
                )
                return
            
            payload = {
                "quantity": quantity,
                "listing_id": listing_payload["l"],
                "discord_id": str(interaction.user.id),
            }
            
            logger.debug(f"Sending stock change request: {payload}")
            
            response = await internal_post(
                f"/threads/market/quantity/{action.lower()}",
                json=payload,
                session=self.bot.session
            )

            if response.get("error"):
                logger.warning(f"Backend returned error for stock change: {response['error']}")
                await interaction.response.send_message(f"❌ {response['error']}", ephemeral=True)
            else:
                logger.info(f"Successfully updated stock for listing {listing_payload['l']}")

                # The backend reports the authoritative before/after quantities;
                # the picker's cached quantity can be stale.
                previous_quantity = response["previous_quantity"]
                new_quantity = response["quantity"]

                await interaction.response.send_message(
                    f"Stock for [{listing_payload['t']}](<https://sc-market.space/market/{listing_payload['l']}>) changed from `{previous_quantity}` to `{new_quantity}`.\n"
                    f"The listing's available quantity is now updated, so buyers will see `{new_quantity}` available.\n"
                    "-# Check all your stock with /stock view"
                )

        except Exception as e:
            logger.error(f"Unexpected error in handle_stock_change: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Action: {action}, Owner: {owner}, Listing: {listing}, Quantity: {quantity}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await send_ephemeral(interaction, "❌ Couldn't update the stock. Please try again in a moment.")

    @app_commands.command(name="view", description="Show your listings with their available quantity and price")
    @app_commands.describe(
        owner='Whose listings to show: Me (default) or one of your orgs',
    )
    async def view_stock(
            self,
            interaction: discord.Interaction,
            owner: str = None,
    ):
        """View stock for market listings"""
        logger.info(f"Stock view requested: user={interaction.user.id}, owner={owner}")
        
        try:
            spectrum_id = parse_owner(owner)
            if spectrum_id:
                listings = await get_org_listings(spectrum_id, interaction.user.id, session=self.bot.session)
            else:
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings:
                logger.debug(f"No listings found for user {interaction.user.id}")
                await interaction.response.send_message(
                    "No listings to show. Create one with `/list` or on sc-market.space.", ephemeral=True
                )
                return

            logger.debug(f"Displaying {len(listings)} listings for user {interaction.user.id}")
            await display_listings_compact(interaction, listings)

        except Exception as e:
            logger.error(f"Unexpected error in view_stock: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Owner: {owner}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await send_ephemeral(interaction, "❌ Couldn't load your listings. Please try again in a moment.")

    @set_stock.autocomplete('listing')
    @add_stock.autocomplete('listing')
    @sub_stock.autocomplete('listing')
    async def update_stock_listing(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        """Enhanced listing autocomplete with error logging"""
        try:
            logger.debug(f"Fetching listings for stock autocomplete: user={interaction.user.id}, current={current}")
            
            spectrum_id = parse_owner(interaction.namespace.owner)
            if spectrum_id:
                listings = await get_org_listings(spectrum_id, interaction.user.id, session=self.bot.session)
            else:
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings:
                logger.debug(f"No listings found for user {interaction.user.id}")
                return []

            choices = [
                          app_commands.Choice(
                              name=f"{listing['title'][:80]} ({int(listing['quantity_available']):,} available)"[:100],
                              value=ujson.dumps(dict(l=listing['listing_id'], t=listing['title'],
                                                     q=int(listing['quantity_available'])))
                          )
                          for listing in listings if
                          current.lower() in listing['title'].lower()
                      ][:25]
            
            logger.debug(f"Generated {len(choices)} listing autocomplete choices for user {interaction.user.id}")
            return choices
            
        except Exception as e:
            logger.error(f"Error in listing autocomplete: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Current: {current}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return empty list on error to avoid breaking the command
            return []

    @set_stock.autocomplete('owner')
    @add_stock.autocomplete('owner')
    @sub_stock.autocomplete('owner')
    @view_stock.autocomplete('owner')
    async def update_stock_owner(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        return await owner_autocomplete(self.bot, interaction, current)
