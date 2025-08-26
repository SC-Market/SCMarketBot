import asyncio
import logging
import os
import traceback
import sys
from datetime import datetime

import aiohttp
import discord

from discord import ChannelType
from discord.ext.commands import Bot

from cogs.admin import Admin
from cogs.lookup import Lookup
from cogs.order import order
from cogs.registration import Registration
from cogs.stock import stock

from util.config import Config
from util.result import Result
from util.discord_sqs_consumer import DiscordSQSManager
from util.logging_config import LoggingConfig

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Setup logging using centralized configuration
logger = LoggingConfig.setup_logging()


class SCMarket(Bot):
    session = None
    discord_sqs_manager = None

    async def setup_hook(self):
        await self.add_cog(Registration(self))
        await self.add_cog(Admin(self))
        await self.add_cog(Lookup(self))
        await self.add_cog(order(self))
        await self.add_cog(stock(self))

        await self.tree.sync()

        # Initialize Discord SQS manager if enabled
        if Config.ENABLE_SQS:
            self.discord_sqs_manager = DiscordSQSManager(self)
            if await self.discord_sqs_manager.initialize():
                # Start consumer in background to avoid blocking main thread
                asyncio.create_task(self.discord_sqs_manager.start_consumer())
                logger.info("Discord SQS consumer started successfully in background")
            else:
                logger.error("Failed to initialize Discord SQS manager")

        # SQS-only mode - no web server needed
        logger.info("Running in SQS-only mode")

        # Initialize aiohttp session
        try:
            self.session = aiohttp.ClientSession()
            logger.info("aiohttp session initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize aiohttp session: {e}")
            self.session = None
            logger.error("Bot initialization failed due to session error")
            return
        
        # Ensure the session is properly initialized
        if self.session and not self.session.closed:
            logger.info("Ready!")
        else:
            logger.error("Failed to initialize aiohttp session")
            logger.error("Bot initialization failed due to session error")
            return

    async def on_command_error(self, interaction, error):
        """Enhanced error handling for command errors"""
        error_type = type(error).__name__
        error_msg = str(error)
        
        logger.error(f"Command error in {interaction.command.name if interaction.command else 'unknown'}: {error_type}: {error_msg}")
        logger.error(f"User: {interaction.user.id} ({interaction.user.name})")
        logger.error(f"Channel: {interaction.channel.id} ({interaction.channel.name if hasattr(interaction.channel, 'name') else 'DM'})")
        logger.error(f"Guild: {interaction.guild.id if interaction.guild else 'DM'} ({interaction.guild.name if interaction.guild else 'DM'})")
        logger.error(f"Full error: {traceback.format_exc()}")
        
        # Send user-friendly error message
        try:
            if interaction.response.is_done():
                await interaction.followup.send("An error occurred while processing your command. Please try again or contact support if the issue persists.", ephemeral=True)
            else:
                await interaction.response.send_message("An error occurred while processing your command. Please try again or contact support if the issue persists.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
    
    async def close(self):
        """Clean up resources when the bot shuts down"""
        logger.info("Bot shutdown initiated, cleaning up resources...")
        
        try:
            if hasattr(self, 'session') and self.session is not None and not self.session.closed:
                await self.session.close()
                logger.info("aiohttp session closed successfully")
        except Exception as e:
            logger.error(f"Error closing aiohttp session: {e}")
        
        try:
            if hasattr(self, 'discord_sqs_manager'):
                await self.discord_sqs_manager.stop_consumer()
                logger.info("Discord SQS manager stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping Discord SQS manager: {e}")
        
        logger.info("Bot shutdown completed")

    def on_error(self, event_method, *args, **kwargs):
        """Enhanced error handling for Discord events"""
        logger.error(f"Error in Discord event {event_method}: {traceback.format_exc()}")
        logger.error(f"Event args: {args}")
        logger.error(f"Event kwargs: {kwargs}")

    async def on_message(self, message):
        """Enhanced message handling with comprehensive logging"""
        if isinstance(message.channel, discord.Thread):
            if not message.author.bot and message.content:
                logger.debug(f"Processing message from {message.author.id} ({message.author.name}) in thread {message.channel.id}")
                
                # Check if session is available
                if not hasattr(self, 'session') or self.session is None or self.session.closed:
                    logger.error("Cannot send message: aiohttp session not available")
                    logger.error(f"Session state: hasattr={hasattr(self, 'session')}, session={self.session}, closed={getattr(self.session, 'closed', 'N/A') if self.session else 'N/A'}")
                    return
                
                try:
                    payload = {
                        "author_id": str(message.author.id),
                        "name": message.author.name,
                        "thread_id": str(message.channel.id),
                        "content": message.content,
                    }
                    
                    logger.debug(f"Sending message to backend: {payload}")
                    
                    async with self.session.post(
                        f'{Config.DISCORD_BACKEND_URL}/threads/message',
                        json=payload
                    ) as resp:
                        response_data = await resp.read()
                        logger.debug(f"Backend response status: {resp.status}, response: {response_data}")
                        
                        if not resp.ok:
                            logger.warning(f"Backend returned non-OK status: {resp.status} - {response_data}")
                        
                except aiohttp.ClientError as e:
                    logger.error(f"Network error sending message to backend: {e}")
                    logger.error(f"Message details: author={message.author.id}, thread={message.channel.id}, content_length={len(message.content)}")
                except asyncio.TimeoutError as e:
                    logger.error(f"Timeout error sending message to backend: {e}")
                    logger.error(f"Message details: author={message.author.id}, thread={message.channel.id}, content_length={len(message.content)}")
                except Exception as e:
                    logger.error(f"Unexpected error sending message to backend: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Message details: author={message.author.id}, thread={message.channel.id}, content_length={len(message.content)}")
                    logger.error(f"Full traceback: {traceback.format_exc()}")

    async def order_placed(self, body):
        """Enhanced order placement with comprehensive logging"""
        logger.info(f"Processing order_placed request: {body}")
        
        try:
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None or self.session.closed:
                logger.error("Discord session is not available or closed")
                logger.error(f"Session state: hasattr={hasattr(self, 'session')}, session={self.session}, closed={getattr(self.session, 'closed', 'N/A') if self.session else 'N/A'}")
                return dict(thread=None, failed=True, message="Discord session unavailable", invite_code=None)
            
            # Convert string IDs to integers and handle data types
            try:
                server_id = int(body.get('server_id')) if body.get('server_id') else None
                channel_id = int(body.get('channel_id')) if body.get('channel_id') else None
                members = [int(member) for member in body.get('members', []) if member]
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to convert IDs to integers: {e}")
                logger.error(f"Raw values: server_id={body.get('server_id')}, channel_id={body.get('channel_id')}, members={body.get('members')}")
                return dict(thread=None, failed=True, message=f"Invalid ID format: {e}", invite_code=None)
            
            # Use order as offer (they have similar structure)
            offer = body.get('order', {})
            
            logger.info(f"Creating thread: server_id={server_id}, channel_id={channel_id}, members={members}")
            logger.debug(f"Offer details: {offer}")
            
            result = await self.create_thread(
                server_id,
                channel_id,
                members,
                offer,
            )

            thread = result.value
            logger.info(f"Thread creation result: {result}")

            # Handle invite creation
            invite = None
            if body.get('server_id') and body.get('channel_id'):
                try:
                    invite = await self.verify_invite(
                        body.get('customer_discord_id'),
                        body.get('server_id'),
                        body.get('channel_id'),
                        body.get("discord_invite")
                    )
                    logger.info(f"Invite verification result: {invite}")
                except Exception as e:
                    logger.error(f"Failed to verify/create invite: {e}")
                    logger.error(f"Invite details: customer_id={body.get('customer_discord_id')}, server_id={body.get('server_id')}, channel_id={body.get('channel_id')}")
                    logger.error(f"Full traceback: {traceback.format_exc()}")
            else:
                logger.info("Skipping invite creation - missing server_id or channel_id")

            if not thread:
                thread = dict(thread_id=None,
                              invite_code=str(invite) if invite else None)

                logger.error(f"Thread creation failed: {result.error}")
                logger.error(f"Result object: {result}")
            else:
                logger.info(f"Thread created successfully: {thread}")
                
            return dict(thread=thread, failed=bool(result.error), message=result.error, invite_code=invite)
            
        except Exception as e:
            logger.error(f"Unexpected error in order_placed: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Request body: {body}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return dict(thread=None, failed=True, message=f"An unexpected error occurred: {e}", invite_code=None)

    async def verify_invite(self, customer_id, server_id, channel_id, invite_code):
        """Enhanced invite verification with comprehensive logging"""
        logger.info(f"Verifying invite: customer_id={customer_id}, server_id={server_id}, channel_id={channel_id}, invite_code={invite_code}")
        
        try:
            guild: discord.Guild = await self.fetch_guild(int(server_id))
            if not guild:
                logger.debug(f"Guild not found for server_id: {server_id} - this may be a configuration issue")
                return None

            channel: discord.TextChannel = guild.get_channel(int(channel_id))
            if not channel:
                logger.debug(f"Channel not found for channel_id: {channel_id} in guild: {guild.name} - this may be a configuration issue")
                return None

            logger.debug(f"Found guild: {guild.name} and channel: {channel.name}")

            # Check if customer is already a member
            try:
                if customer_id:
                    is_member = await guild.fetch_member(int(customer_id))
                    if is_member:
                        logger.info(f"Customer {customer_id} is already a member of guild {guild.name}")
                        return None
            except discord.NotFound:
                logger.debug(f"Customer {customer_id} is not a member of guild {guild.name}")
            except Exception as e:
                logger.warning(f"Error checking if customer is member: {e}")

            # Handle invite creation/verification
            try:
                if invite_code:
                    logger.debug(f"Attempting to fetch existing invite: {invite_code}")
                    invite = await self.fetch_invite(invite_code)
                    if invite:
                        logger.info(f"Existing invite {invite_code} is valid")
                        return invite_code
                    else:
                        logger.debug(f"Existing invite {invite_code} is invalid - this may be a configuration issue")
                else:
                    logger.debug("No existing invite code provided")
                    invite = None

                if not invite:
                    logger.info(f"Creating new invite for channel {channel.name} in guild {guild.name}")
                    new_invite = await channel.create_invite(reason="Invite customer to the guild", unique=False)
                    logger.info(f"Created new invite: {new_invite.code}")
                    return new_invite.code
                    
            except discord.Forbidden as e:
                logger.debug(f"Bot lacks permission to create invites in channel {channel.name}: {e} - this is a configuration issue")
                return None
            except discord.HTTPException as e:
                logger.error(f"HTTP error creating/fetching invite: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error handling invite: {e}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                return None
                
        except discord.NotFound as e:
            logger.debug(f"Guild or channel not found: {e} - this may be a configuration issue")
            return None
        except discord.Forbidden as e:
            logger.debug(f"Bot lacks permission to access guild/channel: {e} - this is a configuration issue")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in verify_invite: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def on_member_join(self, member):
        """Enhanced member join handling with comprehensive logging"""
        logger.info(f"Member joined: {member.id} ({member.name}) in guild {member.guild.id} ({member.guild.name})")
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.debug(f"Fetching threads for user {member.id}")
                
                async with session.get(
                        f'{Config.DISCORD_BACKEND_URL}/threads/user/{member.id}',
                ) as resp:
                    if not resp.ok:
                        logger.error(f"Failed to fetch threads for user {member.id}: {resp.status} - {resp.reason}")
                        return

                    try:
                        result = await resp.json()
                        logger.debug(f"Threads response for user {member.id}: {result}")
                    except Exception as e:
                        logger.error(f"Failed to decode response for user {member.id}: {e}")
                        logger.error(f"Response status: {resp.status}, response text: {await resp.text()}")
                        return

                    if 'thread_ids' not in result:
                        logger.warning(f"Unexpected response format for user {member.id}: {result}")
                        return

                    thread_ids = result['thread_ids']
                    logger.info(f"Found {len(thread_ids)} threads for user {member.id}")

                    guild: discord.Guild = member.guild
                    failed_threads = []
                    
                    for thread_id in thread_ids:
                        try:
                            logger.debug(f"Adding user {member.id} to thread {thread_id}")
                            thread = guild.get_thread(int(thread_id))
                            if thread:
                                await thread.add_user(member)
                                logger.info(f"Successfully added user {member.id} to thread {thread_id}")
                            else:
                                logger.debug(f"Thread {thread_id} not found in guild {guild.name} - this may be a configuration issue")
                                failed_threads.append(thread_id)
                        except discord.Forbidden as e:
                            logger.debug(f"Bot lacks permission to add user {member.id} to thread {thread_id}: {e} - this is a configuration issue")
                            failed_threads.append(thread_id)
                        except discord.NotFound as e:
                            logger.debug(f"Thread {thread_id} not found: {e} - this may be a configuration issue")
                            failed_threads.append(thread_id)
                        except discord.HTTPException as e:
                            logger.error(f"HTTP error adding user {member.id} to thread {thread_id}: {e}")
                            failed_threads.append(thread_id)
                        except Exception as e:
                            logger.error(f"Unexpected error adding user {member.id} to thread {thread_id}: {e}")
                            logger.error(f"Error type: {type(e).__name__}")
                            logger.error(f"Full traceback: {traceback.format_exc()}")
                            failed_threads.append(thread_id)
                    
                    if failed_threads:
                        logger.debug(f"Failed to add user {member.id} to {len(failed_threads)} threads: {failed_threads} - these may be configuration issues")
                    else:
                        logger.info(f"Successfully processed all threads for user {member.id}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"Network error in on_member_join for user {member.id}: {e}")
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout error in on_member_join for user {member.id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in on_member_join for user {member.id}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Full traceback: {traceback.format_exc()}")

    async def create_thread(self, server_id: int, channel_id: int, members: list[int], offer: dict):
        """Enhanced thread creation with comprehensive logging"""
        logger.info(f"Creating thread: server_id={server_id}, channel_id={channel_id}, members={members}")
        logger.debug(f"Offer details: {offer}")
        
        if not server_id or not channel_id or not members:
            error_msg = f"Missing required parameters: server_id={server_id}, channel_id={channel_id}, members={members}"
            logger.error(error_msg)
            return Result(error=error_msg)

        try:
            guild: discord.Guild = await self.fetch_guild(int(server_id))
            if not guild:
                error_msg = f"Bot is not in the configured guild: {server_id}"
                logger.error(error_msg)
                return Result(error=error_msg)
            
            logger.debug(f"Found guild: {guild.name}")

            # Fetch channel with error handling
            try:
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    try:
                        logger.debug(f"Channel {channel_id} not in cache, fetching from Discord...")
                        channel: discord.TextChannel = await guild.fetch_channel(int(channel_id))
                        logger.debug(f"Successfully fetched channel: {channel.name}")
                    except discord.NotFound:
                        error_msg = f"The configured thread channel {channel_id} no longer exists in guild {guild.name}"
                        logger.debug(f"{error_msg} - this is a configuration issue")
                        return Result(error=error_msg)
                    except discord.Forbidden:
                        error_msg = f"The bot does not have permission to view the configured thread channel {channel_id} in guild {guild.name}"
                        logger.debug(f"{error_msg} - this is a configuration issue")
                        return Result(error=error_msg)
                    except discord.InvalidData:
                        error_msg = f"The bot received invalid data from Discord when attempting to fetch the configured thread channel {channel_id}"
                        logger.error(error_msg)
                        return Result(error=error_msg)
                    except Exception as e:
                        error_msg = f"Unexpected error fetching channel {channel_id}: {e}"
                        logger.error(error_msg)
                        logger.error(f"Error type: {type(e).__name__}")
                        logger.error(f"Full traceback: {traceback.format_exc()}")
                        return Result(error=error_msg)
                
                if not channel:
                    error_msg = f"Failed to retrieve channel {channel_id} from guild {guild.name}"
                    logger.error(error_msg)
                    return Result(error=error_msg)
                    
            except Exception as e:
                error_msg = f"Error accessing channel {channel_id}: {e}"
                logger.error(error_msg)
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                return Result(error=error_msg)

            # Determine thread name
            is_order = offer.get("order_id")
            thread_name = f"{'order' if is_order else 'offer'}-{offer.get('id', offer.get('order_id'))[:8]}"
            logger.debug(f"Creating thread with name: {thread_name}")

            # Create thread
            try:
                thread = await channel.create_thread(
                    name=thread_name,
                    type=ChannelType.private_thread
                )
                logger.info(f"Successfully created thread: {thread.id} with name: {thread.name}")
            except discord.Forbidden as e:
                error_msg = f"The bot does not have permission to create threads in channel {channel.name}: {e}"
                logger.debug(f"{error_msg} - this is a configuration issue")
                return Result(error=error_msg)
            except discord.HTTPException as e:
                error_msg = f"HTTP error creating thread in channel {channel.name}: {e}"
                logger.error(error_msg)
                return Result(error=error_msg)
            except Exception as e:
                error_msg = f"Unexpected error creating thread in channel {channel.name}: {e}"
                logger.error(error_msg)
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                return Result(error=error_msg)

            # Add bot to thread
            try:
                await thread.add_user(self.user)
                logger.debug(f"Added bot to thread {thread.id}")
            except Exception as e:
                logger.debug(f"Failed to add bot to thread {thread.id}: {e} - this may be a configuration issue")

            # Add members to thread
            failed_members = []
            for member in members:
                if not member:
                    continue

                try:
                    logger.debug(f"Adding member {member} to thread {thread.id}")
                    await thread.add_user(discord.Object(int(member)))
                    logger.debug(f"Successfully added member {member} to thread {thread.id}")
                except discord.Forbidden as e:
                    logger.debug(f"Bot lacks permission to add member {member} to thread {thread.id}: {e} - this is a configuration issue")
                    failed_members.append(member)
                except discord.NotFound as e:
                    logger.debug(f"Member {member} not found: {e} - this may be a configuration issue")
                    failed_members.append(member)
                except discord.HTTPException as e:
                    logger.error(f"HTTP error adding member {member} to thread {thread.id}: {e}")
                    failed_members.append(member)
                except Exception as e:
                    logger.error(f"Unexpected error adding member {member} to thread {thread.id}: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    failed_members.append(member)

            # Handle failed member additions
            invite = None
            if failed_members:
                logger.debug(f"Failed to add {len(failed_members)} members to thread {thread.id}: {failed_members} - these may be configuration issues")
                
                try:
                    logger.info(f"Creating invite for failed members: {failed_members}")
                    invite = await channel.create_invite(max_uses=len(failed_members))
                    logger.info(f"Created invite: {invite.code}")
                    
                    for member in failed_members:
                        try:
                            user = await self.fetch_user(int(member))
                            invite_message = f"You submitted an offer on SC Market. Please join the fulfillment server to communicate directly with the seller: {invite}"
                            await user.send(invite_message)
                            logger.info(f"Sent invite message to user {member}")
                        except discord.Forbidden as e:
                            logger.debug(f"Cannot send DM to user {member}: {e} - this is a configuration issue")
                        except discord.NotFound as e:
                            logger.debug(f"User {member} not found: {e} - this may be a configuration issue")
                        except Exception as e:
                            logger.error(f"Failed to send invite message to user {member}: {e}")
                            logger.error(f"Error type: {type(e).__name__}")
                            
                except discord.Forbidden as e:
                    logger.debug(f"Bot lacks permission to create invite in channel {channel.name}: {e} - this is a configuration issue")
                except discord.HTTPException as e:
                    logger.error(f"HTTP error creating invite in channel {channel.name}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error creating invite: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Full traceback: {traceback.format_exc()}")

            result_data = dict(thread_id=str(thread.id), failed=failed_members, invite_code=str(invite.code) if invite else None)
            logger.info(f"Thread creation completed successfully: {result_data}")
            return Result(value=result_data)

        except Exception as e:
            error_msg = f"Unexpected error in create_thread: {e}"
            logger.error(error_msg)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Result(error=error_msg)


def main():
    # Validate configuration
    config_issues = Config.validate()
    if config_issues:
        logger.error("Configuration validation failed:")
        for issue, description in config_issues.items():
            logger.error(f"  {issue}: {description}")
        return
    
    # Log startup information
    LoggingConfig.log_startup_info()
    
    bot = SCMarket(intents=intents, command_prefix="/")
    
    try:
        logger.info("Starting bot...")
        bot.run(Config.DISCORD_API_KEY)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down bot...")
    except Exception as e:
        logger.error(f"Unexpected error during bot execution: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
    finally:
        # Log shutdown information
        LoggingConfig.log_shutdown_info()
        logger.info("Bot shutdown completed")

if __name__ == "__main__":
    main()
