import asyncio
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from util.config import Config

logger = logging.getLogger('SCMarketBot.DiscordSQSConsumer')

class DiscordSQSMessage:
    """Represents a message from the Discord queue"""
    
    def __init__(self, message_data: Dict[str, Any]):
        self.type = message_data.get('type')
        self.payload = message_data.get('payload', {})
        self.metadata = message_data.get('metadata', {})
        self.order_id = self.metadata.get('order_id')
        self.entity_type = self.metadata.get('entity_type')
        self.created_at = self.metadata.get('created_at')
        self.retry_count = self.metadata.get('retry_count', 0)

class DiscordSQSResponse:
    """Represents a response to send back to the backend"""
    
    def __init__(self, message_type: str, payload: Dict[str, Any], metadata: Dict[str, Any]):
        self.type = message_type
        self.payload = payload
        self.metadata = metadata
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'payload': self.payload,
            'metadata': {
                **self.metadata,
                'created_at': datetime.utcnow().isoformat() + 'Z'
            }
        }

class DiscordSQSConsumer:
    """Consumes messages from the Discord queue and processes them"""
    
    def __init__(self, bot, sqs_client):
        self.bot = bot
        self.sqs_client = sqs_client
        self.message_handlers = {
            'create_thread': self._handle_create_thread,
            # Add more handlers as needed
        }
    
    async def process_message(self, message_body: Dict[str, Any], raw_message: Dict[str, Any]) -> bool:
        """Process an incoming Discord queue message"""
        try:
            discord_message = DiscordSQSMessage(message_body)
            logger.info(f"Processing {discord_message.type} message for order {discord_message.order_id}")
            
            if discord_message.type in self.message_handlers:
                handler = self.message_handlers[discord_message.type]
                result = await handler(discord_message)
                
                if result:
                    logger.info(f"Successfully processed {discord_message.type} message")
                else:
                    logger.error(f"Failed to process {discord_message.type} message")
                
                return result
            else:
                logger.warning(f"Unknown message type: {discord_message.type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing Discord queue message: {e}")
            return False
    
    async def _handle_create_thread(self, message: DiscordSQSMessage) -> bool:
        """Handle create_thread message type"""
        try:
            payload = message.payload
            
            # Extract required fields
            server_id = payload.get('server_id')
            channel_id = payload.get('channel_id')
            members = payload.get('members', [])
            order = payload.get('order', {})
            customer_discord_id = payload.get('customer_discord_id')
            
            # Validate required fields
            if not all([server_id, channel_id, members]):
                logger.error(f"Missing required fields for create_thread: server_id={server_id}, channel_id={channel_id}, members={members}")
                await self._send_error_response(message, "Missing required fields")
                return False
            
            # Create the thread using existing bot method
            result = await self.bot.order_placed({
                'server_id': server_id,
                'channel_id': channel_id,
                'members': members,
                'order': order,
                'customer_discord_id': customer_discord_id
            })
            
            if result and not result.get('failed'):
                # Send success response
                response = DiscordSQSResponse(
                    'thread_created',
                    {
                        'thread_id': result.get('thread', {}).get('thread_id'),
                        'invite_code': result.get('invite_code'),
                        'success': True
                    },
                    {
                        'discord_message_id': None,  # TODO: Add if we send a welcome message
                        'original_order_id': message.order_id
                    }
                )
                
                await self._send_response(response)
                logger.info(f"Thread created successfully: {result.get('thread', {}).get('thread_id')}")
                return True
            else:
                # Send error response
                error_msg = result.get('message', 'Unknown error') if result else 'No result returned'
                await self._send_error_response(message, error_msg)
                logger.error(f"Thread creation failed: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling create_thread: {e}")
            await self._send_error_response(message, str(e))
            return False
    
    async def _send_response(self, response: DiscordSQSResponse) -> bool:
        """Send a response to the backend queue"""
        try:
            success = await self.sqs_client.send_message(
                Config.BACKEND_QUEUE_URL.split('/')[-1],  # Extract queue name from URL
                response.to_dict()
            )
            
            if success:
                logger.info(f"Response sent successfully: {response.type}")
            else:
                logger.error(f"Failed to send response: {response.type}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending response: {e}")
            return False
    
    async def _send_error_response(self, original_message: DiscordSQSMessage, error_message: str) -> bool:
        """Send an error response to the backend queue"""
        try:
            response = DiscordSQSResponse(
                'error',
                {
                    'error': error_message,
                    'success': False
                },
                {
                    'original_order_id': original_message.order_id,
                    'original_type': original_message.type
                }
            )
            
            return await self._send_response(response)
            
        except Exception as e:
            logger.error(f"Error sending error response: {e}")
            return False

class DiscordSQSManager:
    """Manages the Discord SQS consumer and response handling"""
    
    def __init__(self, bot):
        self.bot = bot
        self.sqs_client = None
        self.consumer = None
        self.consumer_task = None
        
    async def initialize(self):
        """Initialize SQS client and consumer"""
        try:
            from util.sqs_client import SQSClient
            self.sqs_client = SQSClient()
            self.consumer = DiscordSQSConsumer(self.bot, self.sqs_client)
            
            if not self.sqs_client.sqs:
                logger.error("SQS client initialization failed")
                return False
                
            logger.info("Discord SQS manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Discord SQS manager: {e}")
            return False
    
    async def start_consumer(self):
        """Start consuming messages from the Discord queue"""
        if not self.sqs_client or not self.consumer:
            logger.error("Discord SQS manager not initialized")
            return
        
        try:
            # Extract queue name from URL
            queue_name = Config.DISCORD_QUEUE_URL.split('/')[-1]
            
            self.consumer_task = asyncio.create_task(
                self.sqs_client.start_consumer(
                    queue_name,
                    self.consumer.process_message,
                    Config.SQS_CONSUMER_SETTINGS['max_messages'],
                    Config.SQS_CONSUMER_SETTINGS['wait_time']
                )
            )
            
            logger.info(f"Started Discord SQS consumer for queue: {queue_name}")
            
        except Exception as e:
            logger.error(f"Failed to start Discord SQS consumer: {e}")
    
    async def stop_consumer(self):
        """Stop the Discord SQS consumer"""
        if self.consumer_task and not self.consumer_task.done():
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass
        
        self.consumer_task = None
        logger.info("Stopped Discord SQS consumer")
