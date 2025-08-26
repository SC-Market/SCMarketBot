import aiohttp
import logging
import traceback
from typing import Optional, Dict, Any

from cogs.registration import DISCORD_BACKEND_URL

logger = logging.getLogger('SCMarketBot.Fetch')

async def public_fetch(url, params=None, session=None):
    """Enhanced public fetch with comprehensive error logging"""
    tempsession = None
    try:
        if session is None:
            tempsession = aiohttp.ClientSession()
            logger.debug(f"Created temporary session for public fetch to {url}")
        else:
            tempsession = session

        logger.debug(f"Making public fetch request to: {url} with params: {params}")
        
        async with tempsession.get(
                f"https://api.sc-market.space/api{url}",
                params=params
        ) as resp:
            if not resp.ok:
                logger.warning(f"Public API returned non-OK status: {resp.status} for {url}")
                logger.debug(f"Response headers: {dict(resp.headers)}")
            
            result = await resp.json()
            logger.debug(f"Public fetch successful for {url}: {result}")
            return result
            
    except aiohttp.ClientError as e:
        logger.error(f"Network error in public fetch to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise
    except asyncio.TimeoutError as e:
        logger.error(f"Timeout error in public fetch to {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in public fetch to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise
    finally:
        if session is None and tempsession is not None:
            await tempsession.close()
            logger.debug("Closed temporary session for public fetch")


async def internal_fetch(url, params=None, session=None):
    """Enhanced internal fetch with comprehensive error logging"""
    tempsession = None
    try:
        if session is None:
            tempsession = aiohttp.ClientSession()
            logger.debug(f"Created temporary session for internal fetch to {url}")
        else:
            tempsession = session

        logger.debug(f"Making internal fetch request to: {url} with params: {params}")
        
        async with tempsession.get(
                f"{DISCORD_BACKEND_URL}{url}",
                params=params
        ) as resp:
            if not resp.ok:
                logger.warning(f"Internal API returned non-OK status: {resp.status} for {url}")
                logger.debug(f"Response headers: {dict(resp.headers)}")
                try:
                    error_text = await resp.text()
                    logger.debug(f"Error response body: {error_text}")
                except Exception as e:
                    logger.debug(f"Could not read error response body: {e}")
            
            result = await resp.json()
            logger.debug(f"Internal fetch successful for {url}: {result}")
            return result
            
    except aiohttp.ClientError as e:
        logger.error(f"Network error in internal fetch to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise
    except asyncio.TimeoutError as e:
        logger.error(f"Timeout error in internal fetch to {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in internal fetch to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise
    finally:
        if session is None and tempsession is not None:
            await tempsession.close()
            logger.debug("Closed temporary session for internal fetch")


async def internal_post(url, params=None, json=None, session=None):
    """Enhanced internal post with comprehensive error logging"""
    tempsession = None
    try:
        if session is None:
            tempsession = aiohttp.ClientSession()
            logger.debug(f"Created temporary session for internal post to {url}")
        else:
            tempsession = session

        logger.debug(f"Making internal post request to: {url} with params: {params}, json: {json}")
        
        async with tempsession.post(
                f"{DISCORD_BACKEND_URL}{url}",
                params=params,
                json=json,
        ) as resp:
            if not resp.ok:
                logger.warning(f"Internal API returned non-OK status: {resp.status} for {url}")
                logger.debug(f"Response headers: {dict(resp.headers)}")
                try:
                    error_text = await resp.text()
                    logger.debug(f"Error response body: {error_text}")
                except Exception as e:
                    logger.debug(f"Could not read error response body: {e}")
            
            result = await resp.json()
            logger.debug(f"Internal post successful for {url}: {result}")
            return result
            
    except aiohttp.ClientError as e:
        logger.error(f"Network error in internal post to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise
    except asyncio.TimeoutError as e:
        logger.error(f"Timeout error in internal post to {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in internal post to {url}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise
    finally:
        if session is None and tempsession is not None:
            await tempsession.close()
            logger.debug("Closed temporary session for internal post")


async def get_user_orders(discord_id, session=None):
    """Enhanced user orders fetch with error logging"""
    try:
        logger.debug(f"Fetching orders for user {discord_id}")
        response = await internal_fetch(f"/threads/user/{discord_id}/assigned", session=session)
        
        if 'orders' in response:
            orders = response['orders']
            logger.debug(f"Found {len(orders)} orders for user {discord_id}")
            return orders
        else:
            logger.debug(f"Unexpected response format for user {discord_id}: {response}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to fetch orders for user {discord_id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


async def get_user_listings(discord_id, session=None):
    """Enhanced user listings fetch with error logging"""
    try:
        logger.debug(f"Fetching listings for user {discord_id}")
        response = await internal_fetch(f"/threads/user/{discord_id}/listings", session=session)
        
        if 'listings' in response:
            listings = response['listings']
            logger.debug(f"Found {len(listings)} listings for user {discord_id}")
            return listings
        else:
            logger.debug(f"Unexpected response format for user {discord_id}: {response}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to fetch listings for user {discord_id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


async def get_org_listings(contractor_id, discord_id, session=None):
    """Enhanced org listings fetch with error logging"""
    try:
        logger.debug(f"Fetching org listings for contractor {contractor_id}, user {discord_id}")
        response = await internal_fetch(f"/threads/user/{discord_id}/listings/{contractor_id}", session=session)
        
        if 'listings' in response:
            listings = response['listings']
            logger.debug(f"Found {len(listings)} org listings for contractor {contractor_id}")
            return listings
        else:
            logger.debug(f"Unexpected response format for contractor {contractor_id}: {response}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to fetch org listings for contractor {contractor_id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


async def get_user_orgs(discord_id, session=None):
    """Enhanced user orgs fetch with error logging"""
    try:
        logger.debug(f"Fetching orgs for user {discord_id}")
        response = await internal_fetch(f"/threads/user/{discord_id}/contractors", session=session)
        
        if 'contractors' in response:
            contractors = response['contractors']
            logger.debug(f"Found {len(contractors)} contractors for user {discord_id}")
            return contractors
        else:
            logger.debug(f"Unexpected response format for user {discord_id}: {response}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to fetch orgs for user {discord_id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


async def search_users(query, session=None):
    """Enhanced user search with error logging"""
    try:
        logger.debug(f"Searching users with query: {query}")
        response = await public_fetch(f"/profile/search/{query}", session=session)
        logger.debug(f"User search returned {len(response) if isinstance(response, list) else 'unknown'} results")
        return response
        
    except Exception as e:
        logger.error(f"Failed to search users with query '{query}': {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise


async def search_orgs(query, session=None):
    """Enhanced org search with error logging"""
    try:
        logger.debug(f"Searching orgs with query: {query}")
        response = await public_fetch(f"/contractors", params=dict(query=query, sorting='name'), session=session)
        
        if 'items' in response:
            items = response['items']
            logger.debug(f"Org search returned {len(items)} results")
            return items
        else:
            logger.debug(f"Unexpected response format for org search: {response}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to search orgs with query '{query}': {e}")
        logger.error(f"Error type: {type(e).__name__}")
        raise
