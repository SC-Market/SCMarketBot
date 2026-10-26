"""The shared "owner" picker used by /stock, /price and /list.

The owner option is either you ("Me") or one of your orgs. Autocomplete sends a
small JSON payload; users who type instead of picking send plain text. Both are
accepted here, so a typed Spectrum ID works and typing "me" means you.
"""
import json
import logging
from typing import List, Optional

from discord import app_commands

from util.fetch import get_user_orgs

logger = logging.getLogger("SCMarketBot.Owners")

ME = "_ME"
OWNER_HELP = "Whose listings: pick Me or one of your orgs, e.g. Me"


def parse_owner(value: Optional[str]) -> Optional[str]:
    """Return the org Spectrum ID for ``value``, or None when it means yourself."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == ME or text.lower() == "me":
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    if isinstance(data, dict):
        spectrum_id = str(data.get("s") or "").strip()
        return spectrum_id or None
    return text


def owner_value(org: dict) -> str:
    return json.dumps(dict(s=org["spectrum_id"], n=org["name"]))


def build_owner_choices(orgs, current: str) -> List[app_commands.Choice[str]]:
    current = (current or "").lower()
    choices = [
        app_commands.Choice(name=f"{org['name']} ({org['spectrum_id']})"[:100], value=owner_value(org))
        for org in (orgs if isinstance(orgs, list) else [])
        if current in org["name"].lower() or current in org["spectrum_id"].lower()
    ][:24]
    return choices + [app_commands.Choice(name="Me", value=ME)]


async def owner_autocomplete(bot, interaction, current: str) -> List[app_commands.Choice[str]]:
    try:
        orgs = await get_user_orgs(interaction.user.id, session=bot.session)
    except Exception as e:
        logger.error(f"Owner autocomplete failed: {e}")
        orgs = []
    return build_owner_choices(orgs, current)


async def org_autocomplete(bot, interaction, current: str) -> List[app_commands.Choice[str]]:
    """Your orgs as plain Spectrum IDs, for options that take a Spectrum ID."""
    try:
        orgs = await get_user_orgs(interaction.user.id, session=bot.session)
    except Exception as e:
        logger.error(f"Org autocomplete failed: {e}")
        return []
    current = (current or "").lower()
    return [
        app_commands.Choice(name=f"{org['name']} ({org['spectrum_id']})"[:100], value=org["spectrum_id"])
        for org in (orgs if isinstance(orgs, list) else [])
        if current in org["name"].lower() or current in org["spectrum_id"].lower()
    ][:25]
