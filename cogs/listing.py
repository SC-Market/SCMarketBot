"""/listing — create, reprice, restock, view and import your market listings.

- ``/listing create [owner]``: a fill-in form for a new listing.
- ``/listing price owner listing new_price``
- ``/listing stock owner listing mode quantity``: set, add or subtract.
- ``/listing view [owner]``: your listings with stock and price.
- ``/listing import source username``: copy your listings from another marketplace.

``owner`` is you ("Me") or one of your orgs (see util/owners.py).
"""
import json
import logging
import traceback
from typing import List

import aiohttp
import discord
import ujson
from discord import app_commands
from discord.ext import commands

from util.errors import send_ephemeral
from util.fetch import get_org_listings, get_user_listings, internal_post
from util.listings import display_listings_compact
from util.owners import OWNER_HELP, owner_autocomplete, parse_owner

logger = logging.getLogger("SCMarketBot.ListingCog")

SITE = "https://sc-market.space"
UEX_API_BASE = "https://api.uexcorp.space/2.0"
LISTING_HELP = "The listing to change; pick from the list, e.g. Pembroke Armor Set"

# mode option -> backend route suffix (POST /threads/market/quantity/:opt)
STOCK_MODES = {"set": "set", "add": "add", "subtract": "sub"}
STOCK_MODE_CHOICES = [
    app_commands.Choice(name="Set to this number", value="set"),
    app_commands.Choice(name="Add this many (restocked)", value="add"),
    app_commands.Choice(name="Subtract this many (sold elsewhere)", value="subtract"),
]
IMPORT_SOURCES = [app_commands.Choice(name="UEXCorp", value="uex")]


def _listing_link(listing_payload: dict) -> str:
    return f"[{listing_payload['t']}](<{SITE}/market/{listing_payload['l']}>)"


def _parse_listing(listing: str):
    try:
        payload = json.loads(listing)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) and "l" in payload else None


async def _owner_listings(bot, interaction):
    spectrum_id = parse_owner(interaction.namespace.owner)
    if spectrum_id:
        return await get_org_listings(spectrum_id, interaction.user.id, session=bot.session)
    return await get_user_listings(interaction.user.id, session=bot.session)


class CreateListingModal(discord.ui.Modal, title="Create a Listing"):
    listing_title = discord.ui.TextInput(label="Title", placeholder="e.g. Pembroke Armor Set", max_length=200)
    price = discord.ui.TextInput(label="Price (aUEC)", placeholder="e.g. 50000", max_length=15)
    quantity = discord.ui.TextInput(label="Quantity", placeholder="e.g. 1", default="1", max_length=10)
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
        try:
            price_val = int(self.price.value.replace(",", "").replace(" ", ""))
            if price_val <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ The price must be a whole number above 0, e.g. 50000.", ephemeral=True)
            return

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

        response = await internal_post("/threads/market/create", json=payload, session=self.bot.session)

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't create the listing: {response['error']}", ephemeral=True)
            return

        listing_id = response.get("listing_id", "")
        embed = discord.Embed(
            title="Listing Created",
            description=f"**{self.listing_title.value}**\nPrice: {price_val:,} aUEC\nQuantity: {quantity_val:,}",
            color=0x10B881,
            url=f"{SITE}/market/{listing_id}" if listing_id else None,
        )
        embed.add_field(
            name="What's next",
            value=(
                "Your listing is now live on the market and buyers can find and order it.\n"
                "-# Reprice with /listing price · change stock with /listing stock · see yours with /listing view"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class UEXImportView(discord.ui.View):
    """Confirmation buttons for /listing import."""

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
            json={"discord_id": self.discord_id, "listings": self.listings},
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"❌ Couldn't import: {response['error']}", ephemeral=True)
        else:
            count = response.get("imported", len(self.listings))
            embed = discord.Embed(
                title="Import Complete",
                description=(
                    f"Successfully imported **{count}** listing(s) from UEX.\n"
                    f"View them at [sc-market.space/market/manage]({SITE}/market/manage)"
                ),
                color=0x10B881,
            )
            embed.add_field(
                name="What's next",
                value=(
                    "Your imported listings are now live on SC Market, and buyers can find them with `/search`.\n"
                    "-# Change prices or stock with /listing price and /listing stock, or at "
                    f"{SITE}/market/manage"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel_import(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Import cancelled.", ephemeral=True)
        self.stop()


def map_uex_listings(uex_listings: list) -> list:
    """Active UEX sell listings, in the shape POST /threads/market/import-uex takes (50 at most)."""
    active = [l for l in uex_listings if l.get("operation") == "sell" and not l.get("is_sold_out")]
    return [
        {
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
        for uex in active[:50]
    ]


class Listing(
    commands.GroupCog,
    group_name="listing",
    group_description="Create, reprice, restock, view and import your market listings",
):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="create", description="Create a new market listing with a fill-in form")
    @app_commands.describe(owner="Who sells it: Me (default) or one of your orgs, e.g. Me")
    async def create(self, interaction: discord.Interaction, owner: str = None):
        await interaction.response.send_modal(CreateListingModal(self.bot, parse_owner(owner)))

    @app_commands.command(name="price", description="Change the price of one of your listings")
    @app_commands.describe(owner=OWNER_HELP, listing=LISTING_HELP, new_price="New price in aUEC, e.g. 50000")
    async def price(self, interaction: discord.Interaction, owner: str, listing: str, new_price: int):
        if new_price <= 0:
            await interaction.response.send_message("❌ The price must be greater than 0 aUEC.", ephemeral=True)
            return
        listing_payload = _parse_listing(listing)
        if not listing_payload:
            await interaction.response.send_message(
                "❌ Pick the listing from the suggestions list instead of typing it.", ephemeral=True
            )
            return

        response = await internal_post(
            "/threads/market/price",
            json={"discord_id": str(interaction.user.id), "listing_id": listing_payload["l"], "price": new_price},
            session=self.bot.session,
        )
        if response.get("error"):
            await interaction.response.send_message(f"❌ Couldn't update the price: {response['error']}", ephemeral=True)
            return
        old_price = listing_payload.get("p", 0)
        await interaction.response.send_message(
            f"Price for {_listing_link(listing_payload)} updated from `{old_price:,}` to `{new_price:,}` aUEC.\n"
            "Buyers now see the new price on the listing.\n"
            "-# Change stock with /listing stock · see all your listings with /listing view"
        )

    @app_commands.command(name="stock", description="Set, add to or subtract from a listing's available quantity")
    @app_commands.describe(
        owner=OWNER_HELP,
        listing=LISTING_HELP,
        mode="Set the quantity to this number, or add or subtract it",
        quantity="How many, e.g. 10",
    )
    @app_commands.choices(mode=STOCK_MODE_CHOICES)
    async def stock(
        self,
        interaction: discord.Interaction,
        owner: str,
        listing: str,
        mode: app_commands.Choice[str],
        quantity: int,
    ):
        await self.change_stock(interaction, mode.value, listing, quantity)

    async def change_stock(self, interaction: discord.Interaction, mode: str, listing: str, quantity: int):
        logger.info("Stock change requested: user=%s mode=%s quantity=%s", interaction.user.id, mode, quantity)
        listing_payload = _parse_listing(listing)
        if not listing_payload:
            await interaction.response.send_message(
                "❌ Pick the listing from the suggestions list instead of typing it.", ephemeral=True
            )
            return
        try:
            response = await internal_post(
                f"/threads/market/quantity/{STOCK_MODES[mode]}",
                json={
                    "quantity": quantity,
                    "listing_id": listing_payload["l"],
                    "discord_id": str(interaction.user.id),
                },
                session=self.bot.session,
            )
            if response.get("error"):
                await interaction.response.send_message(f"❌ {response['error']}", ephemeral=True)
                return

            # The backend reports the authoritative before/after quantities;
            # the picker's cached quantity can be stale.
            previous_quantity = response["previous_quantity"]
            new_quantity = response["quantity"]
            await interaction.response.send_message(
                f"Stock for {_listing_link(listing_payload)} changed from `{previous_quantity}` to `{new_quantity}`.\n"
                f"The listing's available quantity is now updated, so buyers will see `{new_quantity}` available.\n"
                "-# Check all your stock with /listing view"
            )
        except Exception:
            logger.error("Stock change failed: %s", traceback.format_exc())
            await send_ephemeral(interaction, "❌ Couldn't update the stock. Please try again in a moment.")

    @app_commands.command(name="view", description="Show your listings with their available quantity and price")
    @app_commands.describe(owner="Whose listings to show: Me (default) or one of your orgs")
    async def view(self, interaction: discord.Interaction, owner: str = None):
        try:
            spectrum_id = parse_owner(owner)
            if spectrum_id:
                listings = await get_org_listings(spectrum_id, interaction.user.id, session=self.bot.session)
            else:
                listings = await get_user_listings(interaction.user.id, session=self.bot.session)

            if not listings or not isinstance(listings, list):
                await interaction.response.send_message(
                    "No listings to show. Create one with `/listing create` or on sc-market.space.", ephemeral=True
                )
                return
            await display_listings_compact(interaction, listings)
        except Exception:
            logger.error("Listing view failed: %s", traceback.format_exc())
            await send_ephemeral(interaction, "❌ Couldn't load your listings. Please try again in a moment.")

    @app_commands.command(name="import", description="Copy your sell listings from another marketplace onto SC Market")
    @app_commands.describe(source="The marketplace to import from", username="Your username there, e.g. spacetrader")
    @app_commands.choices(source=IMPORT_SOURCES)
    async def import_listings(
        self,
        interaction: discord.Interaction,
        source: app_commands.Choice[str],
        username: str,
    ):
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
                            f"❌ Couldn't read listings from UEX (HTTP {resp.status}). "
                            f"Check that the username `{username}` is right.",
                            ephemeral=True,
                        )
                        return
                    data = await resp.json()

            if data.get("status") != "ok":
                await interaction.followup.send("❌ UEX returned an error. Please try again later.", ephemeral=True)
                return

            mapped = map_uex_listings(data.get("data", []))
            if not mapped:
                await interaction.followup.send(
                    f"No active sell listings found for `{username}` on UEX.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"Import from UEX: {username}",
                description=f"Found **{len(mapped)}** active sell listing(s) to import.\n\n",
                color=0x5865F2,
            )
            preview = [
                f"**{i + 1}.** {l['title']} — {l['price']:,} aUEC (x{l['quantity']})" for i, l in enumerate(mapped[:10])
            ]
            if len(mapped) > 10:
                preview.append(f"*... and {len(mapped) - 10} more*")
            embed.description += "\n".join(preview)
            embed.set_footer(text="Click 'Import All' to create these listings on SC Market")

            view = UEXImportView(self.bot, mapped, str(interaction.user.id))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching UEX listings: {e}")
            await interaction.followup.send("❌ Couldn't connect to UEX. Please try again later.", ephemeral=True)

    @price.autocomplete("listing")
    async def price_listing_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            listings = await _owner_listings(self.bot, interaction)
            if not isinstance(listings, list):
                return []
            return [
                app_commands.Choice(
                    name=f"{l['title'][:80]} ({int(l.get('price', l.get('price_min', 0))):,} aUEC)"[:100],
                    value=ujson.dumps(dict(l=l["listing_id"], t=l["title"], p=int(l.get("price", l.get("price_min", 0))))),
                )
                for l in listings
                if current.lower() in l["title"].lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in price listing autocomplete: {e}")
            return []

    @stock.autocomplete("listing")
    async def stock_listing_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            listings = await _owner_listings(self.bot, interaction)
            if not isinstance(listings, list):
                return []
            return [
                app_commands.Choice(
                    name=f"{l['title'][:80]} ({int(l['quantity_available']):,} available)"[:100],
                    value=ujson.dumps(dict(l=l["listing_id"], t=l["title"], q=int(l["quantity_available"]))),
                )
                for l in listings
                if current.lower() in l["title"].lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in stock listing autocomplete: {e}")
            return []

    @create.autocomplete("owner")
    @price.autocomplete("owner")
    @stock.autocomplete("owner")
    @view.autocomplete("owner")
    async def listing_owner_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await owner_autocomplete(self.bot, interaction, current)
