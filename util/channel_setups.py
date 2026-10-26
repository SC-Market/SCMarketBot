"""Client for the backend's /channel-setups routes (what a channel gets, for whom)."""
import logging
from typing import Optional, Tuple

import aiohttp

from util.config import Config
from util.fetch import _seg

logger = logging.getLogger("SCMarketBot.ChannelSetups")

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
UNREACHABLE = "Couldn't reach SC Market. Please try again in a moment."


async def request(method: str, path: str, json: Optional[dict] = None) -> Tuple[int, dict]:
    """(status, body) for a /channel-setups call; status 0 when the backend is unreachable."""
    url = f"{Config.discord_backend_base()}/channel-setups{path}"
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.request(method, url, json=json) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = {}
                if not isinstance(body, dict):
                    body = {}
                if resp.status >= 500:
                    logger.error("channel-setups %s %s failed: %s %s", method, path, resp.status, body)
                return resp.status, body
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.error("channel-setups %s %s unreachable: %s", method, path, e)
        return 0, {"error": UNREACHABLE}


def error_text(status: int, body: dict) -> str:
    return f"❌ {body.get('error') or UNREACHABLE}"


async def save(kind: str, interaction, org: Optional[str]) -> Tuple[int, dict]:
    payload = {
        "kind": kind,
        "discord_id": str(interaction.user.id),
        "channel_id": str(interaction.channel_id),
        "guild_id": str(interaction.guild_id),
    }
    if org:
        payload["spectrum_id"] = org
    return await request("POST", "", payload)


async def status(channel_id) -> Tuple[int, dict]:
    return await request("GET", f"/{_seg(channel_id)}")


async def remove(kind: str, interaction, org: Optional[str]) -> Tuple[int, dict]:
    payload = {"kind": kind, "discord_id": str(interaction.user.id)}
    if org:
        payload["spectrum_id"] = org
    return await request("DELETE", f"/{_seg(interaction.channel_id)}", payload)
