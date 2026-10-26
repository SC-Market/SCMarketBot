"""
Buy/Offer modals used by the /search result buttons, and the /import uex command.
"""
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post

logger = logging.getLogger('SCMarketBot.MarketplaceCog')

UEX_API_BASE = "https://api.uexcorp.space/2.0"


class BuyModal(discord.ui.Modal, title="Place Order"):
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="1",
        default="1",
        max_length=10,
    )
    note = discord.ui.TextInput(
        label="Note to Seller (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Pickup location preference, timing, etc.",
        max_length=500,
        required=False,
    )

    def __init__(self, bot, listing_id: str, listing_title: str, price: int):
        super().__init__()
        self.bot = bot
        self.listing_id = listing_id
        self.listing_title = listing_title
        self.price = price

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value.replace(",", "").strip())
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The quantity must be a whole number above 0, e.g. 1.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        response = await internal_post(
            "/threads/market/buy",
            json={
                "discord_id": str(interaction.user.id),
                "listing_id": self.listing_id,
                "quantity": qty,
                "note": self.note.value or None,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't place the order: {response['error']}", ephemeral=True)
        else:
            total = self.price * qty
            embed = discord.Embed(
                title="Order Placed",
                description=f"**{self.listing_title}** x{qty}\n"
                            f"Total: {total:,} aUEC\n\n"
                            f"The seller has been notified. Check your DMs or fulfillment thread for updates.",
                color=0x10b881,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class OfferModal(discord.ui.Modal, title="Make an Offer"):
    offer_amount = discord.ui.TextInput(
        label="Your Offer (aUEC)",
        placeholder="e.g. 45000",
        max_length=15,
    )
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="1",
        default="1",
        max_length=10,
    )
    message = discord.ui.TextInput(
        label="Message to Seller",
        style=discord.TextStyle.paragraph,
        placeholder="Why should the seller accept your offer?",
        max_length=500,
        required=False,
    )

    def __init__(self, bot, listing_id: str, listing_title: str):
        super().__init__()
        self.bot = bot
        self.listing_id = listing_id
        self.listing_title = listing_title

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.offer_amount.value.replace(",", "").strip())
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The offer must be a whole number of aUEC above 0, e.g. 45000.", ephemeral=True)
            return

        try:
            qty = int(self.quantity.value.replace(",", "").strip())
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The quantity must be a whole number above 0, e.g. 1.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        response = await internal_post(
            "/threads/market/offer",
            json={
                "discord_id": str(interaction.user.id),
                "listing_id": self.listing_id,
                "amount": amount,
                "quantity": qty,
                "message": self.message.value or None,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't send the offer: {response['error']}", ephemeral=True)
        else:
            embed = discord.Embed(
                title="Offer Sent",
                description=f"**{self.listing_title}** x{qty}\n"
                            f"Your offer: {amount:,} aUEC\n\n"
                            f"The seller will be notified. You'll hear back when they respond.",
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class UEXImportView(discord.ui.View):
    """Confirmation view for UEX import."""

    def __init__(self, bot, listings: list, discord_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.listings = listings
        self.discord_id = discord_id

    @discord.ui.button(label="Import All", style=discord.ButtonStyle.green)
    async def import_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        response = await internal_post(
            "/threads/market/import-uex",
            json={
                "discord_id": self.discord_id,
                "listings": self.listings,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't import: {response['error']}", ephemeral=True)
        else:
            count = response.get("imported", len(self.listings))
            embed = discord.Embed(
                title="Import Complete",
                description=f"Successfully imported **{count}** listing(s) from UEX.\n"
                            f"View them at [sc-market.space/market/manage](https://sc-market.space/market/manage)",
                color=0x10b881,
            )
            embed.add_field(
                name="What's next",
                value="Your imported listings are now live on SC Market and buyers can find "
                      "them through `/search`, `/lookup user`, and `/lookup org`.\n"
                      "-# Edit prices, stock, or delist any item at https://sc-market.space/market/manage",
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel_import(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Import cancelled.", ephemeral=True)
        self.stop()


class Marketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    import_group = app_commands.Group(name="import", description="Copy your listings from another marketplace onto SC Market")

    @import_group.command(name="uex", description="Import your UEXCorp sell listings onto SC Market")
    @app_commands.describe(
        username='Your UEXCorp username, e.g. spacetrader',
    )
    async def import_uex(
            self,
            interaction: discord.Interaction,
            username: str,
    ):
        """Import your listings from UEXCorp"""
        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{UEX_API_BASE}/marketplace_listings/",
                    params={"username": username},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            f"Failed to fetch listings from UEX (HTTP {resp.status}). "
                            f"Check that the username `{username}` is correct.",
                            ephemeral=True,
                        )
                        return

                    data = await resp.json()

            if data.get("status") != "ok":
                await interaction.followup.send("UEX API returned an error. Please try again later.", ephemeral=True)
                return

            uex_listings = data.get("data", [])
            if not uex_listings:
                await interaction.followup.send(
                    f"No active listings found for UEX user `{username}`.",
                    ephemeral=True,
                )
                return

            # Filter to active sell listings only
            active_listings = [
                l for l in uex_listings
                if l.get("operation") == "sell" and not l.get("is_sold_out")
            ]

            if not active_listings:
                await interaction.followup.send(
                    f"No active sell listings found for `{username}` on UEX.",
                    ephemeral=True,
                )
                return

            # Map UEX listings to SC Market format
            mapped_listings = []
            for uex in active_listings[:50]:
                mapped = {
                    "title": uex.get("title", "Untitled"),
                    "description": (uex.get("description") or "").replace("\\r\\n", "\n").strip(),
                    "price": int(uex.get("price", 0)),
                    "quantity": int(uex.get("in_stock", 1)),
                    "quality": uex.get("quality"),
                    "durability": uex.get("durability"),
                    "location": uex.get("location", ""),
                    "source": uex.get("source", ""),
                    "uex_id": uex.get("id"),
                }
                mapped_listings.append(mapped)

            # Build summary embed
            embed = discord.Embed(
                title=f"Import from UEX: {username}",
                description=f"Found **{len(mapped_listings)}** active sell listing(s) to import.\n\n",
                color=0x5865F2,
            )

            # Show first 10 items as preview
            preview_lines = []
            for i, listing in enumerate(mapped_listings[:10]):
                preview_lines.append(
                    f"**{i+1}.** {listing['title']} — {listing['price']:,} aUEC (x{listing['quantity']})"
                )
            if len(mapped_listings) > 10:
                preview_lines.append(f"*... and {len(mapped_listings) - 10} more*")

            embed.description += "\n".join(preview_lines)
            embed.set_footer(text="Click 'Import All' to create these listings on SC Market")

            view = UEXImportView(self.bot, mapped_listings, str(interaction.user.id))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching UEX listings: {e}")
            await interaction.followup.send("Failed to connect to UEX. Please try again later.", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in import_uex: {e}")
            await interaction.followup.send("An unexpected error occurred.", ephemeral=True)
