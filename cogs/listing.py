import logging

import discord
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_post
from util.owners import owner_autocomplete, parse_owner

logger = logging.getLogger('SCMarketBot.ListingCog')


class CreateListingModal(discord.ui.Modal, title="Create a Listing"):
    listing_title = discord.ui.TextInput(
        label="Title",
        placeholder="e.g. Pembroke Armor Set",
        max_length=200,
    )
    price = discord.ui.TextInput(
        label="Price (aUEC)",
        placeholder="e.g. 50000",
        max_length=15,
    )
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g. 1",
        default="1",
        max_length=10,
    )
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Describe your item, condition, pickup location, etc.",
        max_length=1000,
        required=False,
    )

    def __init__(self, bot, contractor_spectrum_id=None):
        super().__init__()
        self.bot = bot
        self.contractor_spectrum_id = contractor_spectrum_id

    async def on_submit(self, interaction: discord.Interaction):
        # Validate price
        try:
            price_val = int(self.price.value.replace(",", "").replace(" ", ""))
            if price_val <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The price must be a whole number above 0, e.g. 50000.", ephemeral=True)
            return

        # Validate quantity
        try:
            quantity_val = int(self.quantity.value.replace(",", "").replace(" ", ""))
            if quantity_val <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The quantity must be a whole number above 0, e.g. 1.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        payload = {
            "discord_id": str(interaction.user.id),
            "title": self.listing_title.value,
            "description": self.description.value or self.listing_title.value,
            "price": price_val,
            "quantity": quantity_val,
        }

        if self.contractor_spectrum_id:
            payload["contractor_spectrum_id"] = self.contractor_spectrum_id

        response = await internal_post(
            "/threads/market/create",
            json=payload,
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(
                f"❌ Couldn't create the listing: {response['error']}",
                ephemeral=True,
            )
        else:
            listing_id = response.get("listing_id", "")
            embed = discord.Embed(
                title="Listing Created",
                description=f"**{self.listing_title.value}**\n"
                            f"Price: {price_val:,} aUEC\n"
                            f"Quantity: {quantity_val:,}",
                color=0x10b881,
                url=f"https://sc-market.space/market/{listing_id}" if listing_id else None,
            )
            embed.add_field(
                name="What's next",
                value=(
                    "Your listing is now live on the market and buyers can find and order it.\n"
                    "-# Reprice with /price · update quantity with /stock set · view yours with /lookup user"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class Listing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="list", description="Create a new market listing via a fill-in form")
    @app_commands.describe(
        owner='Who sells it: Me (default) or one of your orgs, e.g. Me',
    )
    async def create_listing(
            self,
            interaction: discord.Interaction,
            owner: str = None,
    ):
        """Create a new market listing"""
        contractor_spectrum_id = parse_owner(owner)
        modal = CreateListingModal(self.bot, contractor_spectrum_id)
        await interaction.response.send_modal(modal)

    @create_listing.autocomplete('owner')
    async def listing_owner_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ):
        return await owner_autocomplete(self.bot, interaction, current)
