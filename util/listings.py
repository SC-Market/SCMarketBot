import datetime
from typing import List

import discord
from discord.ext.paginators.button_paginator import ButtonPaginator

from util.iter import chunks

# V2 sorting methods mapped to API params
v2_sorting_methods = {
    'created_at': "Date Listed (Newest)",
    'price': "Price (Low to High)",
    'quality': "Quality (High to Low)",
    'seller_rating': "Seller Rating",
    'quantity': "Quantity Available",
}

v2_item_types = ["armor", "clothing", "weapon", "paint", "bundle", "flair", "addon", "consumable", "other"]


def create_stock_embed(entries: List[str]):
    embed = discord.Embed(url=f"https://sc-market.space/market/manage?quantityAvailable=0",
                          title="My Stock")
    body = '\n'.join(entries)
    embed.description = f"""```ansi\n{body}\n```"""
    embed.timestamp = datetime.datetime.now()

    return embed


async def display_listings_compact(interaction: discord.Interaction, alllistings: list):
    pages = []
    for listings in chunks(alllistings, 10):
        mq = max(3, *(len(f"{int(l['quantity_available']):,}") for l in listings))
        tq = max(3, *(len(l['title']) for l in listings))
        pq = max(3, *(len(f"{int(l.get('price', l.get('price_min', 0))):,}") for l in listings))

        entries = []
        for listing in listings:
            entries.append(
                f"\u001b[0;40;33m {int(listing['quantity_available']):>{mq},} \u001b[0;40;37m| \u001b[0;40;36m{listing['title']:<{tq}} \u001b[0;40;37m| \u001b[0;40;33m{int(listing.get('price', listing.get('price_min', 0))):>{pq},} \u001b[0;40;36maUEC "
            )

        header = f"\u001b[4;40;37m {'Qt.':<{mq}} | {'Item':<{tq}} | {'Price':>{pq + 5}} "
        entries.insert(0, header)
        pages.append(entries)

    embeds = [create_stock_embed(page) for page in pages]
    paginator = ButtonPaginator(embeds, author_id=interaction.user.id)
    await paginator.send(interaction)


def create_v2_search_embed(listing: dict):
    """Create an embed from a V2 search result."""
    embed = discord.Embed(
        url=f"https://sc-market.space/market/{listing['listing_id']}",
        title=listing['title'],
    )

    # Price display
    price_min = listing.get('price_min', 0)
    price_max = listing.get('price_max', 0)
    if price_min == price_max or price_max == 0:
        embed.add_field(name="Price", value=f"{price_min:,} aUEC")
    else:
        embed.add_field(name="Price", value=f"{price_min:,} - {price_max:,} aUEC")

    # Shop (seller)
    shop_name = listing.get('shop_name', 'Unknown')
    shop_slug = listing.get('shop_slug', '')
    shop_rating = listing.get('shop_rating', 0)
    stars = int(round(shop_rating))
    shop_url = f"https://sc-market.space/shops/{shop_slug}"
    embed.add_field(
        name="Shop",
        value=f"[{shop_name}]({shop_url}) {'⭐' * stars}"
    )

    # Quantity
    embed.add_field(name="Quantity", value=f"{listing.get('quantity_available', 0):,}")

    # Quality tier if present
    qt_min = listing.get('quality_tier_min')
    qt_max = listing.get('quality_tier_max')
    if qt_min or qt_max:
        if qt_min == qt_max:
            embed.add_field(name="Quality", value=f"Tier {qt_min}")
        elif qt_min and qt_max:
            embed.add_field(name="Quality", value=f"Tier {qt_min}-{qt_max}")

    # Item type
    game_item_name = listing.get('game_item_name', '')
    if game_item_name:
        embed.add_field(name="Item", value=game_item_name)

    # Photo
    photo = listing.get('photo')
    if photo:
        embed.set_thumbnail(url=photo)

    # Timestamp
    created_at = listing.get('created_at', '')
    if created_at:
        try:
            embed.timestamp = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    return embed
