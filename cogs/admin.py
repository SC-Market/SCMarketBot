import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Optional

logger = logging.getLogger('SCMarketBot.AdminCog')

class Admin(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot
        # Hardcoded authorized user ID
        self.authorized_user_id = 122739797646245899
        
        # Log admin configuration on startup
        logger.info(f"Admin cog initialized with authorized user ID: {self.authorized_user_id}")
        
    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use admin commands"""
        user_id = interaction.user.id
        
        # Check if user ID matches the authorized ID
        if user_id == self.authorized_user_id:
            logger.debug(f"User {user_id} ({interaction.user.name}) authorized by user ID")
            return True
        
        # Check if user is bot owner (fallback)
        if interaction.user.id == self.bot.application_id:
            logger.debug(f"User {user_id} ({interaction.user.name}) is bot owner")
            return True
        
        # Log unauthorized access attempt
        logger.warning(f"Unauthorized admin command attempt by user {user_id} ({interaction.user.name})")
        logger.warning(f"Authorized user ID: {self.authorized_user_id}")
        
        return False
    
    async def _permission_check(self, interaction: discord.Interaction) -> bool:
        """Permission check decorator for admin commands"""
        if not await self._check_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command. "
                "Only authorized developers can access admin functions.",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="health")
    @app_commands.describe(
        component='The component to check health for (sqs, all)'
    )
    async def health_check(
        self,
        interaction: discord.Interaction,
        component: str = "all"
    ):
        """Check the health status of bot components"""
        # Check permissions first
        if not await self._permission_check(interaction):
            return
        
        logger.info(f"Health check requested by {interaction.user.id} ({interaction.user.name}) for component: {component}")
        
        try:
            if component.lower() == "sqs" or component.lower() == "all":
                await self._check_sqs_health(interaction)
            
            if component.lower() == "all":
                await self._check_general_health(interaction)
                
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            await interaction.followup.send(f"Error during health check: {e}", ephemeral=True)
    
    @app_commands.command(name="restart_sqs")
    async def restart_sqs(self, interaction: discord.Interaction):
        """Manually restart the SQS consumer"""
        # Check permissions first
        if not await self._permission_check(interaction):
            return
        
        logger.info(f"SQS restart requested by {interaction.user.id} ({interaction.user.name})")
        
        try:
            if not hasattr(self.bot, 'discord_sqs_manager') or not self.bot.discord_sqs_manager:
                await interaction.response.send_message("SQS manager not initialized", ephemeral=True)
                return
            
            await interaction.response.send_message("🔄 Restarting SQS consumer...", ephemeral=True)
            
            manager = self.bot.discord_sqs_manager
            
            # Stop current consumer
            await manager.stop_consumer()
            
            # Wait a moment
            import asyncio
            await asyncio.sleep(2)
            
            # Restart consumer
            await manager.start_consumer()
            
            await interaction.followup.send("✅ SQS consumer restarted successfully", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error restarting SQS consumer: {e}")
            await interaction.followup.send(f"❌ Error restarting SQS consumer: {e}", ephemeral=True)
    
    @app_commands.command(name="queue_status")
    async def queue_status(self, interaction: discord.Interaction):
        """Get current SQS queue status"""
        # Check permissions first
        if not await self._permission_check(interaction):
            return
        
        logger.info(f"Queue status requested by {interaction.user.id} ({interaction.user.name})")
        
        try:
            if not hasattr(self.bot, 'discord_sqs_manager') or not self.bot.discord_sqs_manager:
                await interaction.response.send_message("SQS manager not initialized", ephemeral=True)
                return
            
            manager = self.bot.discord_sqs_manager
            if not manager.sqs_client:
                await interaction.response.send_message("SQS client not available", ephemeral=True)
                return
            
            # Extract queue name from URL
            from util.config import Config
            queue_name = Config.DISCORD_QUEUE_URL.split('/')[-1]
            
            # Get queue attributes
            attributes = await manager.sqs_client.get_queue_attributes(queue_name)
            
            if not attributes:
                await interaction.response.send_message("Could not retrieve queue attributes", ephemeral=True)
                return
            
            # Create queue status embed
            embed = discord.Embed(
                title=f"Queue Status: {queue_name}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # Queue depth
            depth = int(attributes.get('ApproximateNumberOfMessages', 0))
            depth_color = "🟢" if depth < 10 else "🟡" if depth < 100 else "🔴"
            embed.add_field(
                name="Queue Depth",
                value=f"{depth_color} {depth} messages",
                inline=True
            )
            
            # In-flight messages
            in_flight = int(attributes.get('ApproximateNumberOfMessagesNotVisible', 0))
            embed.add_field(
                name="In Flight",
                value=f"{in_flight} messages",
                inline=True
            )
            
            # Queue creation time
            if 'CreatedTimestamp' in attributes:
                created_time = int(attributes['CreatedTimestamp'])
                created_date = discord.utils.utcnow().fromtimestamp(created_time)
                embed.add_field(
                    name="Created",
                    value=created_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    inline=True
                )
            
            # Visibility timeout
            if 'VisibilityTimeout' in attributes:
                embed.add_field(
                    name="Visibility Timeout",
                    value=f"{attributes['VisibilityTimeout']}s",
                    inline=True
                )
            
            # Message retention
            if 'MessageRetentionPeriod' in attributes:
                retention_hours = int(attributes['MessageRetentionPeriod']) / 3600
                embed.add_field(
                    name="Message Retention",
                    value=f"{retention_hours:.1f} hours",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            await interaction.response.send_message(f"Error getting queue status: {e}", ephemeral=True)
    
    @app_commands.command(name="admin_info")
    async def admin_info(self, interaction: discord.Interaction):
        """Show admin configuration information (for debugging)"""
        # Check permissions first
        if not await self._permission_check(interaction):
            return
        
        logger.info(f"Admin info requested by {interaction.user.id} ({interaction.user.name})")
        
        try:
            embed = discord.Embed(
                title="Admin Configuration",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # User info
            embed.add_field(
                name="Current User",
                value=f"ID: {interaction.user.id}\nName: {interaction.user.name}",
                inline=False
            )
            
            # User roles
            user_roles = [role.name for role in interaction.user.roles]
            embed.add_field(
                name="User Roles",
                value=", ".join(user_roles) if user_roles else "None",
                inline=False
            )
            
            # Authorization status
            is_authorized = await self._check_permissions(interaction)
            auth_color = "🟢" if is_authorized else "🔴"
            embed.add_field(
                name="Authorization Status",
                value=f"{auth_color} {'Authorized' if is_authorized else 'Unauthorized'}",
                inline=True
            )
            
            # Configuration info
            embed.add_field(
                name="Authorized User ID",
                value=str(self.authorized_user_id),
                inline=True
            )
            
            embed.add_field(
                name="Configuration Type",
                value="Hardcoded User ID",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing admin info: {e}")
            await interaction.response.send_message(f"Error showing admin info: {e}", ephemeral=True)

    async def _check_sqs_health(self, interaction: discord.Interaction):
        """Check SQS consumer health"""
        if not hasattr(self.bot, 'discord_sqs_manager') or not self.bot.discord_sqs_manager:
            await interaction.followup.send("SQS manager not initialized", ephemeral=True)
            return
        
        manager = self.bot.discord_sqs_manager
        health_status = manager.get_health_status()
        
        # Create health status embed
        embed = discord.Embed(
            title="SQS Consumer Health Status",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Basic status
        status_color = "🟢" if health_status['consumer_task_running'] else "🔴"
        embed.add_field(
            name="Consumer Status",
            value=f"{status_color} {'Running' if health_status['consumer_task_running'] else 'Stopped'}",
            inline=True
        )
        
        # Health task status
        health_color = "🟢" if health_status['health_task_running'] else "🔴"
        embed.add_field(
            name="Health Monitor",
            value=f"{health_color} {'Running' if health_status['health_task_running'] else 'Stopped'}",
            inline=True
        )
        
        # Uptime
        uptime_hours = health_status['uptime'] / 3600
        embed.add_field(
            name="Uptime",
            value=f"{uptime_hours:.1f} hours",
            inline=True
        )
        
        # Restart info
        embed.add_field(
            name="Restart Count",
            value=str(health_status['restart_count']),
            inline=True
        )
        
        if health_status['last_restart'] > 0:
            last_restart_hours = (discord.utils.utcnow().timestamp() - health_status['last_restart']) / 3600
            embed.add_field(
                name="Last Restart",
                value=f"{last_restart_hours:.1f} hours ago",
                inline=True
            )
        
        # SQS client health
        if health_status['sqs_health']:
            sqs_health = health_status['sqs_health']
            
            # Client status
            client_color = "🟢" if sqs_health['client_initialized'] else "🔴"
            embed.add_field(
                name="SQS Client",
                value=f"{client_color} {'Initialized' if sqs_health['client_initialized'] else 'Not Initialized'}",
                inline=True
            )
            
            # Message stats
            embed.add_field(
                name="Total Messages",
                value=str(sqs_health['message_count']),
                inline=True
            )
            
            embed.add_field(
                name="Error Count",
                value=str(sqs_health['error_count']),
                inline=True
            )
            
            # Last message time
            if sqs_health['last_message_time'] > 0:
                time_since_last = sqs_health['time_since_last_message']
                if time_since_last < 300:  # 5 minutes
                    last_msg_color = "🟢"
                elif time_since_last < 900:  # 15 minutes
                    last_msg_color = "🟡"
                else:
                    last_msg_color = "🔴"
                
                embed.add_field(
                    name="Last Message",
                    value=f"{last_msg_color} {time_since_last:.1f}s ago",
                    inline=True
                )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _check_general_health(self, interaction: discord.Interaction):
        """Check general bot health"""
        embed = discord.Embed(
            title="General Bot Health",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Session status
        session_healthy = (
            hasattr(self.bot, 'session') and 
            self.bot.session and 
            not self.bot.session.closed
        )
        session_color = "🟢" if session_healthy else "🔴"
        embed.add_field(
            name="HTTP Session",
            value=f"{session_color} {'Healthy' if session_healthy else 'Unhealthy'}",
            inline=True
        )
        
        # Bot latency
        latency = round(self.bot.latency * 1000)
        if latency < 100:
            latency_color = "🟢"
        elif latency < 300:
            latency_color = "🟡"
        else:
            latency_color = "🔴"
        
        embed.add_field(
            name="Bot Latency",
            value=f"{latency_color} {latency}ms",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
