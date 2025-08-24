import asyncio
import json
import logging
import traceback
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
        
        # Extract entity info for easier access
        self.entity_info = self.payload.get('entity_info', {})
        self.entity_id = self.entity_info.get('id')
        self.entity_type_from_payload = self.entity_info.get('type')
        
        # CRITICAL: Log the extracted IDs for debugging
        logger.info(f"DiscordSQSMessage initialized: type={self.type}, order_id={self.order_id}, entity_id={self.entity_id}, entity_type={self.entity_type}")
        
        # Validate that we have the necessary ID for correlation
        if not self.entity_id and not self.order_id:
            logger.warning(f"Message missing both entity_id and order_id - correlation may fail: {message_data}")
        elif self.entity_id and self.order_id and self.entity_id != self.order_id:
            logger.warning(f"Message has different entity_id ({self.entity_id}) and order_id ({self.order_id}) - using entity_id for correlation")

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
            logger.info(f"Raw message body: {message_body}")
            discord_message = DiscordSQSMessage(message_body)
            logger.info(f"Processing {discord_message.type} message for order {discord_message.order_id}")
            
            if discord_message.type in self.message_handlers:
                handler = self.message_handlers[discord_message.type]
                logger.info(f"Calling handler for {discord_message.type}")
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
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def _handle_create_thread(self, message: DiscordSQSMessage) -> bool:
        """Handle create_thread message type"""
        try:
            payload = message.payload
            logger.info(f"Processing create_thread payload: {payload}")
            
            # Extract required fields
            server_id = payload.get('server_id')
            channel_id = payload.get('channel_id')
            members = payload.get('members', [])
            order = payload.get('order', {})
            customer_discord_id = payload.get('customer_discord_id')
            
            # Extract entity info for better correlation
            entity_type = message.entity_type_from_payload or message.entity_type
            entity_id = message.entity_id
            
            # CRITICAL FIX: Use the most reliable source for the business entity ID
            # Priority: entity_id from payload > order_id from metadata > fallback
            business_entity_id = entity_id or message.order_id or "unknown"
            
            logger.info(f"Extracted fields: server_id={server_id}, channel_id={channel_id}, members={members}, entity_type={entity_type}, entity_id={entity_id}")
            logger.info(f"Business entity ID for correlation: {business_entity_id} (from entity_id: {entity_id}, metadata order_id: {message.order_id})")
            
            # Validate required fields
            if not all([server_id, channel_id, members]):
                logger.error(f"Missing required fields for create_thread: server_id={server_id}, channel_id={channel_id}, members={members}")
                await self._send_error_response(message, "Missing required fields")
                return False
            
            # Create the thread using existing bot method
            logger.info(f"Calling bot.order_placed with data: {{'server_id': {server_id}, 'channel_id': {channel_id}, 'members': {members}, 'order': {order}, 'customer_discord_id': {customer_discord_id}}}")
            result = await self.bot.order_placed({
                'server_id': server_id,
                'channel_id': channel_id,
                'members': members,
                'order': order,
                'customer_discord_id': customer_discord_id
            })
            
            logger.info(f"Thread creation result: {result}")
            
            if result and not result.get('failed'):
                # Get the newly created thread ID
                new_thread_id = result.get('thread', {}).get('thread_id')
                
                # CRITICAL FIX: Ensure we're sending the business entity ID, not the thread ID
                logger.info(f"Sending response: thread_id={new_thread_id}, original_order_id={business_entity_id}")
                
                # Send success response
                response = DiscordSQSResponse(
                    'thread_created',
                    {
                        'thread_id': new_thread_id,
                        'invite_code': result.get('invite_code'),
                        'success': True
                    },
                    {
                        'discord_message_id': None,  # TODO: Add if we send a welcome message
                        'original_order_id': business_entity_id,  # ← FIXED: Use business entity ID, not thread ID
                        'entity_type': entity_type,  # Include entity_type for backend correlation
                        'entity_id': entity_id  # Include entity_id for backend correlation
                    }
                )
                
                await self._send_response(response)
                logger.info(f"Thread created successfully: {new_thread_id}")
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
            # Extract entity info from the original message for better correlation
            entity_type = original_message.entity_type_from_payload or original_message.entity_type
            entity_id = original_message.entity_id
            
            # CRITICAL FIX: Use the most reliable source for the business entity ID
            business_entity_id = entity_id or original_message.order_id or "unknown"
            
            logger.info(f"Sending error response: original_order_id={business_entity_id}, error={error_message}")
            
            response = DiscordSQSResponse(
                'error',
                {
                    'error': error_message,
                    'success': False
                },
                {
                    'original_order_id': business_entity_id,  # ← FIXED: Use business entity ID, not potentially corrupted order_id
                    'original_type': original_message.type,
                    'entity_type': entity_type,  # Include entity_type for backend correlation
                    'entity_id': entity_id  # Include entity_id for backend correlation
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
            
            # Start consumer with timeout protection
            self.consumer_task = asyncio.create_task(
                self._run_consumer_with_timeout(queue_name)
            )
            
            logger.info(f"Started Discord SQS consumer for queue: {queue_name}")
            
        except Exception as e:
            logger.error(f"Failed to start Discord SQS consumer: {e}")
    
    async def _run_consumer_with_timeout(self, queue_name: str):
        """Run the consumer with timeout protection to prevent blocking"""
        try:
            # Start a heartbeat task to monitor the consumer
            heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
            
            await asyncio.wait_for(
                self.sqs_client.start_consumer(
                    queue_name,
                    self.consumer.process_message,
                    Config.SQS_CONSUMER_SETTINGS['max_messages'],
                    Config.SQS_CONSUMER_SETTINGS['wait_time']
                ),
                timeout=300  # 5 minute timeout as a safety measure
            )
        except asyncio.TimeoutError:
            logger.warning("SQS consumer timed out, restarting...")
            # Restart the consumer if it times out
            await asyncio.sleep(1)
            await self.start_consumer()
        except Exception as e:
            logger.error(f"SQS consumer error: {e}")
            # Restart the consumer on error
            await asyncio.sleep(5)
            await self.start_consumer()
    
    async def _heartbeat_monitor(self):
        """Monitor the consumer health and log heartbeat"""
        while True:
            try:
                await asyncio.sleep(300)  # Log every 5 minutes instead of every minute
                logger.info("Discord SQS consumer heartbeat - running normally")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}")
                break
    
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
