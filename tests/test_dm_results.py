"""DMs the bot sends are reported to the backend's DM attempt log (util/dm_results.py)."""
import asyncio

from util.config import Config
from util.dm_results import SOURCE_THREAD_INVITE, dm_result_message, report_dm_result


class _HttpError(Exception):
    """Stand-in for discord.Forbidden / NotFound: ``code`` and ``status``."""

    def __init__(self, code, status):
        super().__init__("Cannot send messages to this user")
        self.code = code
        self.status = status


class _FakeSqs:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, queue_name, body):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append((queue_name, body))
        return True


class _Manager:
    def __init__(self, client):
        self.sqs_client = client


class _Bot:
    def __init__(self, client=None):
        self.discord_sqs_manager = _Manager(client) if client else None


def test_sent_message_has_no_error_fields():
    msg = dm_result_message(123456789012345678, SOURCE_THREAD_INVITE)
    assert msg["type"] == "dm_result"
    assert msg["payload"] == {"discord_id": "123456789012345678", "status": "sent", "source": "thread_invite"}
    assert msg["metadata"]["created_at"].endswith("Z")


def test_failed_message_carries_discord_code_and_status():
    msg = dm_result_message("123456789012345678", SOURCE_THREAD_INVITE, _HttpError(50007, 403))
    assert msg["payload"] == {
        "discord_id": "123456789012345678",
        "status": "failed",
        "source": "thread_invite",
        "error_code": 50007,
        "http_status": 403,
    }


def test_failure_without_a_discord_code():
    msg = dm_result_message("123456789012345678", SOURCE_THREAD_INVITE, RuntimeError("network"))
    assert msg["payload"]["status"] == "failed"
    assert msg["payload"]["error_code"] is None
    assert msg["payload"]["http_status"] is None


def test_report_goes_to_the_backend_queue():
    client = _FakeSqs()
    assert asyncio.run(report_dm_result(_Bot(client), "123456789012345678", SOURCE_THREAD_INVITE, _HttpError(50007, 403)))
    [(queue, body)] = client.sent
    assert queue == Config.BACKEND_QUEUE_URL.split('/')[-1]
    assert body["payload"]["error_code"] == 50007


def test_report_never_raises():
    assert asyncio.run(report_dm_result(_Bot(_FakeSqs(fail=True)), "1", SOURCE_THREAD_INVITE)) is False
    assert asyncio.run(report_dm_result(_Bot(None), "1", SOURCE_THREAD_INVITE)) is False
