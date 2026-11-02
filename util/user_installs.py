"""Report users who installed the SC Market app on their own Discord account.

A bot can DM a user who shares a server with it, or who installed the app for
their account (a "user install"). The backend's seller reachability report
counts a seller as reachable by Discord DM only in those two cases; server
membership it reads from the bot's guild member lists, but no Discord API lists
an app's user installs.

What does show it: every interaction carries ``authorizing_integration_owners``.
When the app was user-installed by the person interacting, the USER_INSTALL key
("1") holds that person's Discord id (discord.py:
``Interaction.is_user_integration()``). The bot reports such a user to the
backend as a ``user_install`` message on the backend SQS queue, the
AWS-authenticated queue it already reports DM results on
(tasks/discord-queue-consumer.ts in sc-market-backend). The backend records it
for linked SC Market accounts only, and clears it when a later DM to the user
fails with 50007 (they removed the app or closed their DMs).

Only the Discord user id is sent. One report per user per
REPORT_INTERVAL_SECONDS at most (in memory; a restart may report again, which
the backend treats as "still installed"). Reporting never raises.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from util.config import Config

logger = logging.getLogger('SCMarketBot.UserInstalls')

# At most one report per user this often.
REPORT_INTERVAL_SECONDS = 6 * 60 * 60

# The throttle forgets everyone past this many users (memory bound).
MAX_TRACKED_USERS = 10_000


def user_install_owner(interaction) -> Optional[int]:
    """The Discord id of the user who user-installed the app and is interacting, else None.

    True only when the USER_INSTALL owner is the interacting user: someone
    using a command another user installed is not reported.
    """
    # discord.py: is_user_integration() is
    # authorizing_integration_owners["1"] == interaction.user.id.
    is_user_integration = getattr(interaction, "is_user_integration", None)
    if is_user_integration is None or not is_user_integration():
        return None
    user_id = getattr(getattr(interaction, "user", None), "id", None)
    return int(user_id) if user_id is not None else None


def user_install_message(discord_id) -> Dict[str, Any]:
    """The backend queue message saying this Discord user has the app installed."""
    return {
        "type": "user_install",
        "payload": {"discord_id": str(discord_id)},
        "metadata": {"created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
    }


class UserInstallReporter:
    """Reports user installs seen on interactions, throttled per user."""

    def __init__(self, interval: float = REPORT_INTERVAL_SECONDS, clock=time.monotonic):
        self.interval = interval
        self.clock = clock
        self._last: Dict[int, float] = {}

    def _due(self, discord_id: int) -> bool:
        now = self.clock()
        last = self._last.get(discord_id)
        if last is not None and now - last < self.interval:
            return False
        if len(self._last) >= MAX_TRACKED_USERS:
            self._last.clear()
        self._last[discord_id] = now
        return True

    async def observe(self, bot, interaction) -> bool:
        """Report the interacting user if they user-installed the app. Returns whether a report was queued."""
        try:
            discord_id = user_install_owner(interaction)
            if discord_id is None or not self._due(discord_id):
                return False
            manager = getattr(bot, "discord_sqs_manager", None)
            client = getattr(manager, "sqs_client", None) if manager else None
            if client is None:
                logger.debug("user_install not reported: SQS is not set up")
                return False
            return bool(await client.send_message(
                Config.BACKEND_QUEUE_URL.split('/')[-1],
                user_install_message(discord_id),
            ))
        except Exception as e:  # never fail the interaction
            logger.warning(f"user_install not reported: {type(e).__name__}")
            return False
