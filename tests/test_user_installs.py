"""Users who installed the app on their own account are reported to the backend (util/user_installs.py)."""
import asyncio
from unittest.mock import MagicMock

import discord

from util.config import Config
from util.user_installs import UserInstallReporter, user_install_message, user_install_owner

USER = "111111111111111111"
OTHER = "222222222222222222"


def _interaction(owners, user_id=USER, context=1):
    """A real discord.Interaction parsed from gateway data (state mocked)."""
    data = {
        "id": "1",
        "application_id": "2",
        "type": 2,
        "token": "t",
        "version": 1,
        "attachment_size_limit": 8_000_000,
        "user": {"id": user_id, "username": "u", "discriminator": "0", "avatar": None},
        "authorizing_integration_owners": owners,
        "context": context,
        "data": {"id": "3", "name": "search", "type": 1},
    }
    return discord.Interaction(data=data, state=MagicMock())


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


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_user_install_by_the_interacting_user():
    assert user_install_owner(_interaction({"1": USER})) == int(USER)
    # Installed for the user and the server both.
    assert user_install_owner(_interaction({"0": "999", "1": USER}, context=0)) == int(USER)


def test_guild_install_only_is_not_a_user_install():
    assert user_install_owner(_interaction({"0": "999"}, context=0)) is None
    assert user_install_owner(_interaction({})) is None


def test_someone_elses_user_install_is_not_reported():
    # A command from an app another user installed (e.g. in a group DM).
    assert user_install_owner(_interaction({"1": OTHER})) is None


def test_message_carries_only_the_discord_id():
    msg = user_install_message(int(USER))
    assert msg["type"] == "user_install"
    assert msg["payload"] == {"discord_id": USER}
    assert msg["metadata"]["created_at"].endswith("Z")


def test_reported_to_the_backend_queue_once_per_interval():
    client = _FakeSqs()
    clock = _Clock()
    reporter = UserInstallReporter(interval=60, clock=clock)
    bot = _Bot(client)
    assert asyncio.run(reporter.observe(bot, _interaction({"1": USER})))
    assert not asyncio.run(reporter.observe(bot, _interaction({"1": USER})))
    clock.now = 61
    assert asyncio.run(reporter.observe(bot, _interaction({"1": USER})))
    assert len(client.sent) == 2
    queue, body = client.sent[0]
    assert queue == Config.BACKEND_QUEUE_URL.split('/')[-1]
    assert body["payload"]["discord_id"] == USER


def test_guild_interactions_send_nothing():
    client = _FakeSqs()
    assert not asyncio.run(UserInstallReporter().observe(_Bot(client), _interaction({"0": "999"}, context=0)))
    assert client.sent == []


def test_never_raises():
    assert asyncio.run(UserInstallReporter().observe(_Bot(_FakeSqs(fail=True)), _interaction({"1": USER}))) is False
    assert asyncio.run(UserInstallReporter().observe(_Bot(None), _interaction({"1": USER}))) is False
    assert asyncio.run(UserInstallReporter().observe(_Bot(_FakeSqs()), object())) is False
