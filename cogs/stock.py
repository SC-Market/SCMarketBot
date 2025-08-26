import json
import logging
import traceback
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post, get_user_listings, get_user_orgs, get_org_listings
from util.listings import display_listings_compact

logger = logging.getLogger('SCMarketBot.StockCog')

class stock(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set")
    @app_commands.describe(
        owner='The owner of the listing you want to update. Either you or one of your contractors',
        listing='The listing to modify',
        quantity='The new quantity to set for the listing',
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

    @app_commands.command(name="add")
    @app_commands.describe(
        owner='The owner of the listing you want to update. Either you or one of your contractors',
        listing='The listing to modify',
        quantity='The quantity to add to the listings stock',
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

    @app_commands.command(name="sub")
    @app_commands.describe(
        owner='The owner of the listing you want to update. Either you or one of your contractors',
        listing='The listing to modify',
        quantity='The quantity to subtract from the listings stock',
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
                await interaction.response.send_message("Invalid listing format. Please try again.", ephemeral=True)
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
                await interaction.response.send_message(response['error'])
            else:
                logger.info(f"Successfully updated stock for listing {listing_payload['l']}")
                
                # Calculate new quantity
                newquantity = listing_payload['q']
                if action == "add":
                    newquantity += quantity
                elif action == "sub":
                    newquantity -= quantity
                else:
                    newquantity = quantity

                await interaction.response.send_message(
                    f"Stock for [{listing_payload['t']}](<https://sc-market.space/market/{listing_payload['l']}>) has been set from `{listing_payload['q']}` to `{newquantity}`."
                )

        except Exception as e:
            logger.error(f"Unexpected error in handle_stock_change: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Action: {action}, Owner: {owner}, Listing: {listing}, Quantity: {quantity}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await interaction.response.send_message("An error occurred while updating the stock. Please try again or contact support if the issue persists.", ephemeral=True)

    @app_commands.command(name="view")
    @app_commands.describe(
        owner='The owner of the listing you want to update. Either you or one of your contractors',
    )
    async def view_stock(
            self,
            interaction: discord.Interaction,
            owner: str = None,
    ):
        """View stock for market listings"""
        logger.info(f"Stock view requested: user={interaction.user.id}, owner={owner}")
        
        try:
            if owner and interaction.namespace.owner != "_ME":
                try:
                    owner_payload = json.loads(owner)
                    logger.debug(f"Fetching org listings for contractor {owner_payload['s']}")
                    listings = await get_org_listings(owner_payload['s'], interaction.user.id,
                                                      session=self.bot.session)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse owner JSON: {e}")
                    logger.error(f"Raw owner string: {owner}")
                    await interaction.response.send_message("Invalid owner format. Please try again.", ephemeral=True)
                    return
            else:
                logger.debug(f"Fetching user listings for {interaction.user.id}")
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings:
                logger.debug(f"No listings found for user {interaction.user.id}")
                await interaction.response.send_message("No listings to display", ephemeral=True)
                return

            logger.debug(f"Displaying {len(listings)} listings for user {interaction.user.id}")
            await display_listings_compact(interaction, listings)

        except Exception as e:
            logger.error(f"Unexpected error in view_stock: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Owner: {owner}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await interaction.response.send_message("An error occurred while fetching the listings. Please try again or contact support if the issue persists.", ephemeral=True)

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
            
            if interaction.namespace.owner != "_ME":
                try:
                    owner = json.loads(interaction.namespace.owner)
                    logger.debug(f"Fetching org listings for contractor {owner['s']}")
                    listings = await get_org_listings(owner['s'], interaction.user.id,
                                                      session=self.bot.session)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse owner JSON in autocomplete: {e}")
                    logger.error(f"Raw owner string: {interaction.namespace.owner}")
                    return []
            else:
                logger.debug(f"Fetching user listings for {interaction.user.id}")
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings:
                logger.debug(f"No listings found for user {interaction.user.id}")
                return []

            choices = [
                          app_commands.Choice(
                              name=f"{listing['title'][:100]} ({int(listing['quantity_available']):,} available)",
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
        """Enhanced owner autocomplete with error logging"""
        try:
            logger.debug(f"Fetching orgs for owner autocomplete: user={interaction.user.id}, current={current}")
            orgs = await get_user_orgs(interaction.user.id, session=self.bot.session)

            choices = [
                app_commands.Choice(name=f"{org['name']} ({org['spectrum_id']})",
                                    value=json.dumps(dict(s=org['spectrum_id'], n=org['name'])))
                for org in orgs if
                current.lower() in org['name'].lower() or current.lower() in org['spectrum_id'].lower()
            ][:24] + [app_commands.Choice(name=f"Me", value='_ME')]
            
            logger.debug(f"Generated {len(choices)} owner autocomplete choices for user {interaction.user.id}")
            return choices
            
        except Exception as e:
            logger.error(f"Error in owner autocomplete: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Current: {current}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return basic choices on error to avoid breaking the command
            return [app_commands.Choice(name=f"Me", value='_ME')]
