"""Pure decision logic for Discord order-thread creation.

This module deliberately imports no `discord` or network code so the rules that
decide *what* to do can be unit-tested without a live gateway connection. The
actual Discord I/O lives in ``main.py`` / ``discord_sqs_consumer.py`` and calls
into these helpers.
"""
from __future__ import annotations

from typing import Optional

# Thread-creation strategies returned by :func:`plan_thread_creation`.
STRATEGY_TEXT = "text"  # standard text/announcement channel -> private thread
STRATEGY_FORUM = "forum"  # forum channel -> forum post (no private threads)
STRATEGY_UNSUPPORTED = "unsupported"  # voice/category/etc. -> cannot host threads


def validate_create_thread_fields(
    server_id: object, channel_id: object
) -> Optional[str]:
    """Validate the destination fields for a create_thread request.

    Returns an error string if a required field is missing, otherwise ``None``.

    ``members`` is intentionally NOT required: a thread is still created when the
    member list is empty (nobody has linked Discord yet) so server admins/staff
    can see it, and members are added later if/when they are present.
    """
    if not server_id or not channel_id:
        return (
            f"Missing required fields for create_thread: "
            f"server_id={server_id}, channel_id={channel_id}"
        )
    return None


def plan_thread_creation(channel_type: object) -> str:
    """Map a Discord channel type to a thread-creation strategy.

    Accepts a ``discord.ChannelType`` (uses its ``.name``) or a plain string, so
    it can be exercised in tests without importing ``discord``.
    """
    name = getattr(channel_type, "name", None) or str(channel_type)
    if name == STRATEGY_FORUM:
        return STRATEGY_FORUM
    # Announcement ("news") channels are text channels that also support threads.
    if name in ("text", "news"):
        return STRATEGY_TEXT
    return STRATEGY_UNSUPPORTED


def build_thread_name(offer: dict) -> str:
    """Build the thread name for an order/offer, e.g. ``order-5e9fc632``.

    Preserves the historical naming: prefix from ``order_id`` presence, id from
    ``id`` falling back to ``order_id``.
    """
    is_order = offer.get("order_id")
    entity_id = offer.get("id", offer.get("order_id")) or ""
    prefix = "order" if is_order else "offer"
    return f"{prefix}-{str(entity_id)[:8]}"
