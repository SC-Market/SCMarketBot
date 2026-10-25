from discord import Interaction
from discord.app_commands import MissingPermissions, NoPrivateMessage, check


def guild_manage_channels():
    """Require a guild context and the invoking member's Manage Channels permission.

    Alert subscriptions are configured per channel, so only members who manage
    that channel's server may add or remove them. DMs (``guild_id is None``) are
    rejected outright.
    """

    def predicate(interaction: Interaction) -> bool:
        if interaction.guild_id is None:
            raise NoPrivateMessage("This command can only be used in a server channel.")
        if not interaction.permissions.manage_channels:
            raise MissingPermissions(["manage_channels"])
        return True

    return check(predicate)
