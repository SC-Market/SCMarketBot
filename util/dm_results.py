"""Report every DM the bot sends to the backend, where all DM attempts are kept.

The backend records each Discord DM attempt (sent, or failed with Discord's
error code; 50007 = cannot send messages to this user: DMs closed or no shared
server) in one table, discord_dm_attempts, which the admin seller reachability
report reads. DMs the backend sends are recorded there directly; DMs the bot
sends itself are reported here as a ``dm_result`` message on the backend SQS
queue, the AWS-authenticated queue the bot already answers thread creation on
(tasks/discord-queue-consumer.ts in sc-market-backend). Only the Discord user
id is sent; the backend keeps the attempt only for linked SC Market accounts.

Reporting never raises: a DM that went out is never failed by bookkeeping.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from util.config import Config

logger = logging.getLogger('SCMarketBot.DmResults')

# The fulfilment-server invite sent when someone can't be added to an order thread.
SOURCE_THREAD_INVITE = "thread_invite"


def _int_or_none(value) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def dm_result_message(discord_id, source: str, error: Optional[BaseException] = None) -> Dict[str, Any]:
    """The backend queue message for one DM attempt: sent when ``error`` is None.

    ``error`` is the exception the send raised; discord.py's HTTPException
    (Forbidden, NotFound) carries Discord's JSON error ``code`` and the HTTP
    ``status``.
    """
    payload: Dict[str, Any] = {
        "discord_id": str(discord_id),
        "status": "sent" if error is None else "failed",
        "source": source,
    }
    if error is not None:
        payload["error_code"] = _int_or_none(getattr(error, "code", None))
        payload["http_status"] = _int_or_none(getattr(error, "status", None))
    return {
        "type": "dm_result",
        "payload": payload,
        "metadata": {"created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
    }


async def report_dm_result(bot, discord_id, source: str, error: Optional[BaseException] = None) -> bool:
    """Send one DM attempt to the backend queue. Returns whether it was queued."""
    manager = getattr(bot, "discord_sqs_manager", None)
    client = getattr(manager, "sqs_client", None) if manager else None
    if client is None:
        logger.debug("dm_result not reported: SQS is not set up")
        return False
    try:
        return bool(await client.send_message(
            Config.BACKEND_QUEUE_URL.split('/')[-1],
            dm_result_message(discord_id, source, error),
        ))
    except Exception as e:  # never fail the caller
        logger.warning(f"dm_result not reported: {type(e).__name__}")
        return False
