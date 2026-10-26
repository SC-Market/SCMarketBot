from discord import Interaction
from discord.app_commands import MissingPermissions, NoPrivateMessage, check


def guild_permissions_failure(interaction: Interaction, **perms: bool):
    """The error to raise if ``interaction`` lacks ``perms`` in a guild, else None."""
    if interaction.guild_id is None:
        return NoPrivateMessage("This command can only be used in a server channel.")
    have = interaction.permissions
    missing = [name for name, value in perms.items() if value and not getattr(have, name)]
    if missing:
        return MissingPermissions(missing)
    return None


def require_guild_permissions(**perms: bool):
    """Require a guild context and the invoking member's ``perms`` in this channel.

    DMs (``guild_id is None``) are rejected outright with NoPrivateMessage.
    """

    def predicate(interaction: Interaction) -> bool:
        error = guild_permissions_failure(interaction, **perms)
        if error:
            raise error
        return True

    return check(predicate)


def guild_manage_channels():
    """Require a guild context and the invoking member's Manage Channels permission.

    Order threads and alerts are set up per channel, so only members who manage
    the server's channels may add or remove them.
    """
    return require_guild_permissions(manage_channels=True)


def guild_only():
    """Require a guild context (no permission needed)."""
    return require_guild_permissions()
