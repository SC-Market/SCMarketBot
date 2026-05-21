import logging

import discord
from discord import app_commands
from discord.ext import commands

from util.fetch import internal_fetch, internal_post

logger = logging.getLogger('SCMarketBot.BlueprintCog')

RARITY_LABELS = {1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary"}
RARITY_COLORS = {1: 0x9e9e9e, 2: 0x4caf50, 3: 0x2196f3, 4: 0x9c27b0, 5: 0xff9800}


class Blueprint(commands.GroupCog, group_name="blueprint"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="search")
    @app_commands.describe(
        query="Blueprint name to search for",
    )
    async def blueprint_search(
        self,
        interaction: discord.Interaction,
        query: str,
    ):
        """Search for blueprints/recipes by name"""
        await interaction.response.defer(ephemeral=True)

        response = await internal_fetch(
            "/threads/blueprints/search",
            params={"text": query, "limit": "10"},
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"Search failed: {response['error']}", ephemeral=True)
            return

        blueprints = response.get("blueprints", [])
        if not blueprints:
            await interaction.followup.send(f"No blueprints found for **{query}**.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Blueprint Search: {query}",
            color=0x5865F2,
        )

        for bp in blueprints[:10]:
            rarity = RARITY_LABELS.get(bp.get("rarity", 1), "Unknown")
            output = bp.get("output_item_name") or "Unknown"
            qty = bp.get("output_quantity", 1)
            output_str = f"{output} x{qty}" if qty > 1 else output
            embed.add_field(
                name=bp["blueprint_name"],
                value=f"→ {output_str}\n{rarity} · {bp.get('item_category', 'N/A')}\nID: `{bp['blueprint_id']}`",
                inline=False,
            )

        embed.set_footer(text=f"{len(blueprints)} result(s)")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="conversion")
    @app_commands.describe(
        blueprint="Blueprint ID or name (use /blueprint search to find IDs)",
    )
    async def blueprint_conversion(
        self,
        interaction: discord.Interaction,
        blueprint: str,
    ):
        """Look up the full input → output conversion for a blueprint"""
        await interaction.response.defer(ephemeral=True)

        # If it looks like a name rather than UUID, search first
        blueprint_id = blueprint
        if len(blueprint) != 36 or "-" not in blueprint:
            search = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": blueprint, "limit": "1"},
                session=self.bot.session,
            )
            results = search.get("blueprints", [])
            if not results:
                await interaction.followup.send(f"No blueprint found matching **{blueprint}**.", ephemeral=True)
                return
            blueprint_id = results[0]["blueprint_id"]

        response = await internal_fetch(
            f"/threads/blueprints/conversion/{blueprint_id}",
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"Failed: {response['error']}", ephemeral=True)
            return

        bp_name = response.get("blueprint_name", "Unknown")
        output_item = response.get("output_item", "Unknown")
        output_qty = response.get("output_quantity", 1)
        ingredients = response.get("ingredients", [])
        quality_calc = response.get("quality_calculation")

        embed = discord.Embed(
            title=f"📘 {bp_name}",
            color=0x2196f3,
        )

        # Output
        output_str = f"**{output_item}** x{output_qty}" if output_qty > 1 else f"**{output_item}**"
        embed.add_field(name="Output", value=output_str, inline=False)

        # Ingredients
        if ingredients:
            lines = []
            for ing in ingredients:
                name = ing.get("ingredient_name", "Unknown")
                qty = ing.get("quantity_scu") or ing.get("quantity_required", 1)
                qty_str = f"{float(qty):.2f} SCU" if ing.get("quantity_scu") else f"x{qty}"
                quality_str = f" (min T{ing['min_quality_tier']})" if ing.get("min_quality_tier") else ""
                alt_str = " *(alt)*" if ing.get("is_alternative") else ""
                slot = f"[{ing['slot_display_name']}] " if ing.get("slot_display_name") else ""
                lines.append(f"{slot}**{name}** {qty_str}{quality_str}{alt_str}")

            embed.add_field(
                name="Ingredients",
                value="\n".join(lines) or "None",
                inline=False,
            )

        if quality_calc:
            embed.set_footer(text=f"Quality: {quality_calc.replace('_', ' ').title()}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="own")
    @app_commands.describe(
        blueprint="Blueprint ID or name to register as owned",
        method="How you acquired it (e.g., mission_reward, crafted, purchased)",
    )
    @app_commands.choices(method=[
        app_commands.Choice(name="Mission Reward", value="mission_reward"),
        app_commands.Choice(name="Crafted", value="crafted"),
        app_commands.Choice(name="Purchased", value="purchased"),
        app_commands.Choice(name="Other", value="other"),
    ])
    async def blueprint_own(
        self,
        interaction: discord.Interaction,
        blueprint: str,
        method: app_commands.Choice[str] = None,
    ):
        """Register a blueprint as owned in your inventory"""
        await interaction.response.defer(ephemeral=True)

        # Resolve name to ID if needed
        blueprint_id = blueprint
        if len(blueprint) != 36 or "-" not in blueprint:
            search = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": blueprint, "limit": "1"},
                session=self.bot.session,
            )
            results = search.get("blueprints", [])
            if not results:
                await interaction.followup.send(f"No blueprint found matching **{blueprint}**.", ephemeral=True)
                return
            blueprint_id = results[0]["blueprint_id"]

        response = await internal_post(
            "/threads/blueprints/inventory/add",
            json={
                "discord_id": str(interaction.user.id),
                "blueprint_id": blueprint_id,
                "acquisition_method": method.value if method else "discord",
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"Failed: {response['error']}", ephemeral=True)
        else:
            name = response.get("blueprint_name", blueprint)
            embed = discord.Embed(
                title="Blueprint Registered",
                description=f"**{name}** added to your owned blueprints.",
                color=0x10b881,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="unown")
    @app_commands.describe(
        blueprint="Blueprint ID or name to remove from owned",
    )
    async def blueprint_unown(
        self,
        interaction: discord.Interaction,
        blueprint: str,
    ):
        """Remove a blueprint from your owned inventory"""
        await interaction.response.defer(ephemeral=True)

        blueprint_id = blueprint
        if len(blueprint) != 36 or "-" not in blueprint:
            search = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": blueprint, "limit": "1"},
                session=self.bot.session,
            )
            results = search.get("blueprints", [])
            if not results:
                await interaction.followup.send(f"No blueprint found matching **{blueprint}**.", ephemeral=True)
                return
            blueprint_id = results[0]["blueprint_id"]

        response = await internal_post(
            "/threads/blueprints/inventory/remove",
            json={
                "discord_id": str(interaction.user.id),
                "blueprint_id": blueprint_id,
            },
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"Failed: {response['error']}", ephemeral=True)
        else:
            await interaction.followup.send("Blueprint removed from your inventory.", ephemeral=True)

    @app_commands.command(name="inventory")
    async def blueprint_inventory(self, interaction: discord.Interaction):
        """View your owned blueprints"""
        await interaction.response.defer(ephemeral=True)

        response = await internal_fetch(
            f"/threads/blueprints/inventory/{interaction.user.id}",
            session=self.bot.session,
        )

        if response.get("error"):
            await interaction.followup.send(f"Failed: {response['error']}", ephemeral=True)
            return

        blueprints = response.get("blueprints", [])
        total_owned = response.get("total_owned", 0)
        total_available = response.get("total_available", 0)

        if not blueprints:
            await interaction.followup.send(
                "You don't have any blueprints yet. Use `/blueprint own <name>` to add one.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Your Blueprint Inventory",
            description=f"**{total_owned}** / {total_available} blueprints owned ({total_owned * 100 // max(total_available, 1)}%)",
            color=0x5865F2,
        )

        for bp in blueprints[:25]:
            rarity = RARITY_LABELS.get(bp.get("rarity", 1), "?")
            output = bp.get("output_item_name") or "?"
            embed.add_field(
                name=bp["blueprint_name"],
                value=f"→ {output} · {rarity}",
                inline=True,
            )

        if total_owned > 25:
            embed.set_footer(text=f"Showing 25 of {total_owned}. View all on sc-market.space")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @blueprint_search.autocomplete('query')
    async def blueprint_search_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        if len(current) < 2:
            return []
        try:
            response = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": current, "limit": "25"},
                session=self.bot.session,
            )
            return [
                app_commands.Choice(
                    name=bp["blueprint_name"][:100],
                    value=bp["blueprint_id"],
                )
                for bp in response.get("blueprints", [])
            ][:25]
        except Exception as e:
            logger.error(f"Blueprint autocomplete error: {e}")
            return []

    @blueprint_conversion.autocomplete('blueprint')
    async def conversion_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        if len(current) < 2:
            return []
        try:
            response = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": current, "limit": "25"},
                session=self.bot.session,
            )
            return [
                app_commands.Choice(
                    name=bp["blueprint_name"][:100],
                    value=bp["blueprint_id"],
                )
                for bp in response.get("blueprints", [])
            ][:25]
        except Exception as e:
            logger.error(f"Blueprint autocomplete error: {e}")
            return []

    @blueprint_own.autocomplete('blueprint')
    async def own_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        if len(current) < 2:
            return []
        try:
            response = await internal_fetch(
                "/threads/blueprints/search",
                params={"text": current, "limit": "25"},
                session=self.bot.session,
            )
            return [
                app_commands.Choice(
                    name=bp["blueprint_name"][:100],
                    value=bp["blueprint_id"],
                )
                for bp in response.get("blueprints", [])
            ][:25]
        except Exception as e:
            logger.error(f"Blueprint autocomplete error: {e}")
            return []

    @blueprint_unown.autocomplete('blueprint')
    async def unown_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        try:
            response = await internal_fetch(
                f"/threads/blueprints/inventory/{interaction.user.id}",
                session=self.bot.session,
            )
            blueprints = response.get("blueprints", [])
            if current:
                blueprints = [bp for bp in blueprints if current.lower() in bp["blueprint_name"].lower()]
            return [
                app_commands.Choice(
                    name=bp["blueprint_name"][:100],
                    value=bp["blueprint_id"],
                )
                for bp in blueprints
            ][:25]
        except Exception as e:
            logger.error(f"Blueprint unown autocomplete error: {e}")
            return []
