import json
import logging
import traceback
from typing import List

import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.errors import is_expired_interaction, send_private_after_public_defer
from util.fetch import internal_post, get_user_orders

logger = logging.getLogger('SCMarketBot.OrderCog')

class order(commands.GroupCog, group_description="Update the orders assigned to you or your org"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="status",
        description="Update an order's status from its thread or by selecting the order",
    )
    @app_commands.describe(
        order='Order to update; leave blank to use the current order thread, e.g. Medical Supplies x5',
        newstatus='New status to set, e.g. Fulfilled',
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
            # Local checks answer straight away; the backend call is deferred
            # first so a slow response can't outlast Discord's 3-second window.
            order_payload = None
            if order is None:
                if not isinstance(interaction.channel, discord.Thread):
                    logger.debug(f"User {interaction.user.id} tried to update status outside of thread")
                    await interaction.response.send_message(
                        "❌ This isn't an order thread, so pick the order in the `order` option.", ephemeral=True
                    )
                    return
                logger.debug(f"Updating status for thread {interaction.channel.id} to {newstatus}")
                body = {
                    "status": newstatus,
                    "thread_id": str(interaction.channel.id),
                    "discord_id": str(interaction.user.id),
                }
            else:
                try:
                    order_payload = json.loads(order)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse order JSON: {e}")
                    logger.error(f"Raw order string: {order}")
                    await interaction.response.send_message(
                        "❌ Pick the order from the suggestions list instead of typing it.", ephemeral=True
                    )
                    return
                logger.debug(f"Updating status for specific order {order_payload.get('o')} to {newstatus}")
                body = {
                    "status": newstatus,
                    "order_id": order_payload['o'],
                    "discord_id": str(interaction.user.id),
                }

            await interaction.response.defer(thinking=True)
            response = await internal_post("/threads/order/status", json=body, session=self.bot.session)

            if response.get("error"):
                logger.warning(f"Backend returned error for status update: {response['error']}")
                await send_private_after_public_defer(interaction, f"❌ {response['error']}")
            else:
                logger.info(f"Successfully updated order status to {newstatus}")
                if order_payload:
                    await interaction.followup.send(
                        f"Successfully updated the status to {newstatus} for order '[{order_payload['t']}](<https://sc-market.space/contract/{order_payload['o']}>)'\n\n"
                        f"The customer and the order thread have been notified, and the new status now shows on the order.\n"
                        f"-# Change it again with /order status · open the order using the link above"
                    )
                else:
                    await interaction.followup.send(
                        f"Successfully updated status for the order\n\n"
                        f"The customer and this order thread have been notified, and the new status now shows on the order.\n"
                        f"-# Change it again with /order status"
                    )

        except Exception as e:
            if is_expired_interaction(e):
                logger.info("command_expired name=order status")
                return
            logger.error(f"Unexpected error in update_status: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"User: {interaction.user.id}, Status: {newstatus}, Order: {order}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            await send_private_after_public_defer(
                interaction, "❌ Couldn't update the order status. Please try again in a moment."
            )

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
