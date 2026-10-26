"""Buy and Offer modals behind the /search result buttons (no slash commands)."""
import logging

import discord

from util.fetch import internal_post

logger = logging.getLogger('SCMarketBot.MarketplaceCog')


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
