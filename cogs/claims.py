"""Claim Order / Claim Offer buttons on the alerts that /setup alerts posts.

The buttons' custom IDs (``claim_order:<id>``, ``claim_offer:<id>``) are
stable, so alerts posted before a bot update keep working.
"""
import logging

import aiohttp
import discord
from discord.ext import commands

from util.config import Config

logger = logging.getLogger("SCMarketBot.Claims")

DISCORD_BACKEND_URL = Config.discord_backend_base()


class Claims(commands.Cog):
    """The Claim Order / Claim Offer buttons on order alerts (no slash commands)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button clicks for order/offer claiming."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id.startswith("claim_order:"):
            await self._handle_claim(interaction, "order", custom_id.split(":")[1])
        elif custom_id.startswith("claim_offer:"):
            await self._handle_claim(interaction, "offer", custom_id.split(":")[1])

    async def _handle_claim(self, interaction: discord.Interaction, claim_type: str, entity_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            body = {"discord_id": str(interaction.user.id)}
            if claim_type == "order":
                body["order_id"] = entity_id
            else:
                body["session_id"] = entity_id

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{DISCORD_BACKEND_URL}/claim/{claim_type}",
                    json=body,
                ) as resp:
                    data = await resp.json()

                    if not resp.ok or not data.get("success"):
                        error = data.get("error", "Unknown error")
                        # Remove the claim button if the backend says the state is invalid
                        if data.get("remove_button"):
                            try:
                                await interaction.message.edit(view=None)
                            except Exception:
                                pass
                        await interaction.followup.send(f"❌ {error}", ephemeral=True)
                        return

                    display_name = data.get("display_name", interaction.user.display_name)

                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label=f"Claimed by {display_name}",
                        style=discord.ButtonStyle.secondary,
                        disabled=True,
                        custom_id=f"claim_{claim_type}:{entity_id}",
                    ))
                    await interaction.message.edit(view=view)
                    await interaction.followup.send(
                        f"✅ You've been assigned to this {claim_type}!\n"
                        f"You're now the owner of this {claim_type}; open the fulfillment thread to coordinate and complete it.\n"
                        "-# See what this channel gets with /setup status",
                        ephemeral=True,
                    )

        except Exception as e:
            logger.error(f"Failed to handle claim {claim_type}: {e}")
            await interaction.followup.send(f"❌ An error occurred while claiming this {claim_type}.", ephemeral=True)
