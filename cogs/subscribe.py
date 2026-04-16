import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp

logger = logging.getLogger('SCMarketBot.SubscribeCog')

DISCORD_BACKEND_URL = os.environ.get("DISCORD_BACKEND_URL", "http://localhost:8081")


class AlertSubscriptions(commands.Cog):
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
                    await interaction.followup.send(f"✅ You've been assigned to this {claim_type}!", ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to handle claim {claim_type}: {e}")
            await interaction.followup.send(f"❌ An error occurred while claiming this {claim_type}.", ephemeral=True)

    subscribe_group = app_commands.Group(name="subscribe", description="Manage alert subscriptions")

    @subscribe_group.command(name="alerts", description="Subscribe this channel to order/offer alerts for an organization")
    @app_commands.describe(org_name="The spectrum ID of the organization")
    async def subscribe_alerts(self, interaction: discord.Interaction, org_name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{DISCORD_BACKEND_URL}/alert-subscriptions",
                    json={
                        "channel_id": str(interaction.channel_id),
                        "guild_id": str(interaction.guild_id),
                        "spectrum_id": org_name,
                        "discord_id": str(interaction.user.id),
                    },
                ) as resp:
                    data = await resp.json()
                    if not resp.ok:
                        await interaction.followup.send(f"❌ {data.get('error', 'Unknown error')}", ephemeral=True)
                        return
                    embed = discord.Embed(
                        title="✅ Alert Subscription Active",
                        description=f"This channel will now receive order and offer alerts for **{org_name}**.\n\nMembers with the **Claim Orders** permission can click the button on alerts to assign themselves.",
                        color=0x10b881,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to subscribe alerts: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @subscribe_group.command(name="alerts_user", description="Subscribe this channel to your personal order/offer alerts")
    async def subscribe_alerts_user(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{DISCORD_BACKEND_URL}/alert-subscriptions",
                    json={
                        "channel_id": str(interaction.channel_id),
                        "guild_id": str(interaction.guild_id),
                        "discord_id": str(interaction.user.id),
                    },
                ) as resp:
                    data = await resp.json()
                    if not resp.ok:
                        await interaction.followup.send(f"❌ {data.get('error', 'Unknown error')}", ephemeral=True)
                        return
                    embed = discord.Embed(
                        title="✅ Alert Subscription Active",
                        description="This channel will now receive your personal order and offer alerts.",
                        color=0x10b881,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to subscribe user alerts: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    unsubscribe_group = app_commands.Group(name="unsubscribe", description="Remove subscriptions")

    @unsubscribe_group.command(name="alerts", description="Remove order/offer alert subscription from this channel")
    async def unsubscribe_alerts(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{DISCORD_BACKEND_URL}/alert-subscriptions/{interaction.channel_id}",
                ) as resp:
                    if resp.status == 404:
                        await interaction.followup.send("❌ No alert subscription found for this channel.", ephemeral=True)
                        return
                    if not resp.ok:
                        await interaction.followup.send("❌ Failed to remove subscription.", ephemeral=True)
                        return
                    await interaction.followup.send("✅ Alert subscription removed from this channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to unsubscribe alerts: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)
