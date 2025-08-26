import json
import logging
import traceback
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post, get_user_orders

logger = logging.getLogger('SCMarketBot.OrderCog')

class order(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status")
    @app_commands.describe(
        order='The order to update',
        newstatus='The new status to set the order to',
    )
    @app_commands.choices(
        newstatus=[
            app_commands.Choice(name=name, value=value) for name, value in
            [("Fulfilled", "fulfilled"), ("In Progress", "in-progress"), ("Cancelled", "cancelled")]
        ],
    )
    async def update_status(
            self,
            interaction: discord.Interaction,
            newstatus: str,
            order: str = None,
    ):
        """Set the new status for the order in the current thread"""
        logger.info(f"Order status update requested: user={interaction.user.id}, status={newstatus}, order={order}")
        
        try:
            if order is None:
                if isinstance(interaction.channel, discord.Thread):
                    logger.debug(f"Updating status for thread {interaction.channel.id} to {newstatus}")
                    response = await internal_post("/threads/order/status",
                                                   json={
                                                       "status": newstatus,
                                                       "thread_id": str(interaction.channel.id),
                                                       "discord_id": str(interaction.user.id)
                                                   },
                                                   session=self.bot.session)
                else:
                    logger.debug(f"User {interaction.user.id} tried to update status outside of thread")
                    await interaction.response.send_message("No order in this channel. Please select an order to update.")
                    return
            else:
                try:
                    order_payload = json.loads(order)
                    logger.debug(f"Updating status for specific order {order_payload.get('o')} to {newstatus}")
                    response = await internal_post(
                        "/threads/order/status",
                        json={
                            "status": newstatus,
                            "order_id": order_payload['o'],
                            "discord_id": str(interaction.user.id)
                        },
                        session=self.bot.session
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse order JSON: {e}")
                    logger.error(f"Raw order string: {order}")
                    await interaction.response.send_message("Invalid order format. Please try again.", ephemeral=True)
                    return

            if response.get("error"):
                logger.warning(f"Backend returned error for status update: {response['error']}")
                await interaction.response.send_message(response['error'])
            else:
                logger.info(f"Successfully updated order status to {newstatus}")
                if order:
                    await interaction.response.send_message(
                        f"Successfully updated the status to {newstatus} for order '[{order_payload['t']}](<https://sc-market.space/contract/{order_payload['o']}>)'"
                    )
                else:
                    await interaction.response.send_message(f"Successfully updated status for the order")

        except Exception as e:
            logger.error(f"Unexpected error in update_status: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Status: {newstatus}, Order: {order}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await interaction.response.send_message("An error occurred while updating the order status. Please try again or contact support if the issue persists.", ephemeral=True)

    @update_status.autocomplete('order')
    async def update_status_order_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        """Enhanced autocomplete with error logging"""
        try:
            logger.debug(f"Fetching orders for autocomplete: user={interaction.user.id}, current={current}")
            orders = await get_user_orders(interaction.user.id, session=self.bot.session)
            
            if not orders:
                logger.debug(f"No orders found for user {interaction.user.id}")
                return []
            
            choices = [
                app_commands.Choice(name=order['title'],
                                    value=ujson.dumps(dict(t=order['title'], o=order['order_id'])))
                for order in orders if
                (current.lower() in order['title'].lower() or current.lower() in order['description'].lower()) and
                order['status'] != interaction.namespace.newstatus
            ]
            
            logger.debug(f"Generated {len(choices)} autocomplete choices for user {interaction.user.id}")
            return choices

        except Exception as e:
            logger.error(f"Error in order autocomplete: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Current: {current}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return empty list on error to avoid breaking the command
            return []
