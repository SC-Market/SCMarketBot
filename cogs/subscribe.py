import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp

from util.checks import guild_manage_channels
from util.config import Config
from util.owners import org_autocomplete

logger = logging.getLogger('SCMarketBot.SubscribeCog')

# Single source of truth for the internal discord_app base URL (pinned in Config).
DISCORD_BACKEND_URL = Config.discord_backend_base()


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
                        "-# Manage this channel's alerts with /unsubscribe alerts",
                        ephemeral=True,
                    )

        except Exception as e:
            logger.error(f"Failed to handle claim {claim_type}: {e}")
            await interaction.followup.send(f"❌ An error occurred while claiming this {claim_type}.", ephemeral=True)

    subscribe_group = app_commands.Group(
        name="subscribe",
        description="Post new orders and offers in this channel with a Claim button (needs Manage Channels)",
    )

    @subscribe_group.command(name="alerts", description="Post your org's new orders and offers in this channel, with a Claim button")
    @app_commands.describe(org_name="Your org's Spectrum ID; pick from the list, e.g. SCMARKET")
    @guild_manage_channels()
    async def subscribe_alerts(self, interaction: discord.Interaction, org_name: str):
        await interaction.response.defer(ephemeral=True)
        await create_alert_subscription(interaction, org_name)

    @subscribe_alerts.autocomplete("org_name")
    async def subscribe_alerts_org_autocomplete(self, interaction: discord.Interaction, current: str):
        return await org_autocomplete(self.bot, interaction, current)

    @subscribe_group.command(name="alerts_user", description="Post new offers sent to you personally in this channel")
    @guild_manage_channels()
    async def subscribe_alerts_user(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_alert_subscription(interaction, None)

    unsubscribe_group = app_commands.Group(
        name="unsubscribe",
        description="Stop posting order and offer alerts in this channel (needs Manage Channels)",
    )

    @unsubscribe_group.command(name="alerts", description="Stop posting order and offer alerts in this channel")
    @guild_manage_channels()
    async def unsubscribe_alerts(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{DISCORD_BACKEND_URL}/alert-subscriptions/{interaction.channel_id}",
                    json={"discord_id": str(interaction.user.id)},
                ) as resp:
                    if resp.status == 404:
                        await interaction.followup.send(
                            "❌ This channel isn't receiving alerts, so there's nothing to remove.\n"
                            "-# Run /unsubscribe alerts in the channel where the alerts are posted.",
                            ephemeral=True,
                        )
                        return
                    if resp.status == 403:
                        data = await resp.json()
                        await interaction.followup.send(f"❌ {data.get('error', 'You cannot remove this subscription.')}", ephemeral=True)
                        return
                    if not resp.ok:
                        await interaction.followup.send("❌ Couldn't remove the alerts. Please try again in a moment.", ephemeral=True)
                        return
                    await interaction.followup.send(
                        "✅ Alert subscription removed from this channel.\n"
                        "This channel will stop receiving alerts.\n"
                        "-# Turn them back on with /setup or /subscribe alerts",
                        ephemeral=True,
                    )
        except Exception as e:
            logger.error(f"Failed to unsubscribe alerts: {e}")
            await interaction.followup.send("❌ Couldn't reach SC Market. Please try again in a moment.", ephemeral=True)


def subscription_success_embed(org_name):
    """What the channel will now receive, and who can act on it."""
    if org_name:
        description = (
            f"New orders and offers for **{org_name}** will be posted here as they come in, "
            "each with a **Claim** button."
        )
        claim = (
            "Org members with the **Claim Orders** role permission on SC Market can click **Claim** "
            "to assign the order or offer to themselves. Orders that already have an assignee aren't posted."
        )
    else:
        description = "New offers sent to you personally will be posted here as they come in."
        claim = "Personal offers are already yours, so they have no Claim button; open the link to reply."
    embed = discord.Embed(title="✅ Alerts are on for this channel", description=description, color=0x10b881)
    embed.add_field(name="Claiming", value=claim, inline=False)
    embed.add_field(
        name="What's next",
        value=(
            "Want a private thread with the buyer for each order too? Run `/setup` and pick **Order threads**.\n"
            "-# Stop with /unsubscribe alerts · one alert setup per channel; subscribing again replaces it"
        ),
        inline=False,
    )
    return embed


async def create_alert_subscription(interaction: discord.Interaction, org_name):
    """POST /alert-subscriptions for this channel and report the outcome (interaction already deferred).

    ``org_name`` is the org's Spectrum ID, or None for personal alerts. Returns True on success.
    """
    org_name = (org_name or "").strip() or None
    body = {
        "channel_id": str(interaction.channel_id),
        "guild_id": str(interaction.guild_id),
        "discord_id": str(interaction.user.id),
    }
    if org_name:
        body["spectrum_id"] = org_name
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{DISCORD_BACKEND_URL}/alert-subscriptions", json=body) as resp:
                data = await resp.json()
                if not resp.ok:
                    await interaction.followup.send(f"❌ {data.get('error', 'Unknown error')}", ephemeral=True)
                    return False
    except Exception as e:
        logger.error(f"Failed to subscribe alerts: {e}")
        await interaction.followup.send("❌ Couldn't reach SC Market. Please try again in a moment.", ephemeral=True)
        return False
    await interaction.followup.send(embed=subscription_success_embed(org_name), ephemeral=True)
    return True
