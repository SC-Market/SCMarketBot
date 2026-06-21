import datetime
from typing import List

import discord
import humanize
from discord.ext.paginators.button_paginator import ButtonPaginator

from util.iter import chunks

categories = ["Armor", "Clothing", "Weapon", "Paint", "Bundle", "Flair", "Addon", "Consumable", "Other"]
sorting_methods = {
    'title': "Title",
    'price-low': "Price (Low to High)",
    'price-high': "Price (High to Low)",
    'quantity-low': "Quantity Available (Low to High)",
    'quantity-high': "Quantity Available (High to Low)",
    'date-new': "Date Listed (Old to New)",
    'date-old': "Date Listed (New to Old)",
    'activity': "Recent Activity",
    'rating': "Rating (High to Low)",
}

sale_types = ["Aggregate", "Auction", "Sale"]

# V2 sorting methods mapped to API params
v2_sorting_methods = {
    'created_at': "Date Listed (Newest)",
    'price': "Price (Low to High)",
    'quality': "Quality (High to Low)",
    'seller_rating': "Seller Rating",
    'quantity': "Quantity Available",
}

v2_item_types = ["armor", "clothing", "weapon", "paint", "bundle", "flair", "addon", "consumable", "other"]


def create_market_embed(listing: dict):
    embed = discord.Embed(url=f"https://sc-market.space/market/{listing['listing_id']}", title=listing['title'])
    embed.add_field(name="Item Type", value=listing['item_type'].capitalize())
    if listing["listing_type"] != "unique":
        embed.add_field(name="Minimum Price", value=f"{int(listing['minimum_price']):,} aUEC")
        embed.add_field(name="Maximum Price", value=f"{int(listing['maximum_price']):,} aUEC")
    else:
        embed.add_field(name="Price", value=f"{int(listing['price']):,} aUEC")
        embed.add_field(
            name="Seller",
            value=f"[{listing['contractor_seller'] or listing['user_seller']}]({'https://sc-market.space/contractor/' + listing['contractor_seller'] if listing['contractor_seller'] else 'https://sc-market.space/user/' + listing['user_seller']}) {'⭐' * int(round(listing['avg_rating']))}"
        )

    if listing['auction_end_time'] is not None:
        date = datetime.datetime.strptime(listing['auction_end_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
        embed.add_field(name="Auction End", value="Ending " + humanize.naturaltime(date))

    embed.add_field(name="Quantity Available", value=f"{int(listing['quantity_available']):,}")

    embed.set_image(url=listing['photo'])
    embed.timestamp = datetime.datetime.strptime(listing['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ')

    return embed


def create_market_embed_individual(listing: dict):
    embed = discord.Embed(url=f"https://sc-market.space/market/{listing['listing']['listing_id']}",
                          title=listing['details']['title'])
    embed.add_field(name="Item Type", value=listing['details']['item_type'].capitalize())
    embed.add_field(name="Price", value=f"{int(listing['listing']['price']):,} aUEC")
    seller = listing['listing'].get('contractor_seller') or listing['listing'].get('user_seller')
    embed.add_field(
        name="Seller",
        value=f"[{seller.get('name') or seller.get('display_name')}]({'https://sc-market.space/contractor/' + seller['spectrum_id'] if listing['listing'].get('contractor_seller') else 'https://sc-market.space/user/' + seller['username']}) {'⭐' * int(round(seller['rating']['avg_rating'] / 10))}"
    )

    if listing.get('auction_details') and listing['auction_details']['auction_end_time'] is not None:
        date = datetime.datetime.strptime(listing['auction_details']['auction_end_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
        embed.add_field(name="Auction End", value="Ending " + humanize.naturaltime(date))

    embed.add_field(name="Quantity Available", value=f"{int(listing['listing']['quantity_available']):,}")

    embed.set_image(url=listing['photos'][0] if listing[
        'photos'] else "https://cdn.robertsspaceindustries.com/static/images/Temp/default-image.png")
    embed.timestamp = datetime.datetime.strptime(listing['listing']['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ')

    return embed


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


def create_v2_detail_embed(data: dict):
    """Create an embed from a V2 listing detail response."""
    listing_data = data['listing']
    seller = data['seller']
    items = data.get('items', [])

    embed = discord.Embed(
        url=f"https://sc-market.space/market/{listing_data['listing_id']}",
        title=listing_data['title'],
        description=(listing_data.get('description', '') or '')[:200],
    )

    # Price from items/variants
    all_prices = []
    total_quantity = 0
    for item in items:
        if item.get('pricing_mode') == 'unified' and item.get('base_price'):
            all_prices.append(item['base_price'])
        for variant in item.get('variants', []):
            if variant.get('price'):
                all_prices.append(variant['price'])
            total_quantity += variant.get('quantity', 0)

    if all_prices:
        p_min, p_max = min(all_prices), max(all_prices)
        if p_min == p_max:
            embed.add_field(name="Price", value=f"{p_min:,} aUEC")
        else:
            embed.add_field(name="Price", value=f"{p_min:,} - {p_max:,} aUEC")

    # Shop (seller)
    stars = int(round(seller.get('rating', 0)))
    shop_url = f"https://sc-market.space/shops/{seller['slug']}"
    embed.add_field(
        name="Shop",
        value=f"[{seller['name']}]({shop_url}) {'⭐' * stars}"
    )

    embed.add_field(name="Quantity", value=f"{total_quantity:,}")
    embed.add_field(name="Status", value=listing_data.get('status', 'active').capitalize())

    # Photos
    photos = listing_data.get('photos', [])
    if photos:
        embed.set_image(url=photos[0])

    try:
        embed.timestamp = datetime.datetime.fromisoformat(listing_data['created_at'].replace('Z', '+00:00'))
    except (ValueError, AttributeError, KeyError):
        pass

    return embed
