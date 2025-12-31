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
        logger.debug(f"DiscordSQSMessage initialized: type={self.type}, order_id={self.order_id}, entity_id={self.entity_id}, entity_type={self.entity_type}")
        
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
        message_id = raw_message.get('MessageId', 'unknown')
        receipt_handle = raw_message.get('ReceiptHandle', 'unknown')
        
        logger.debug(f"Processing message {message_id} from Discord queue")
        logger.debug(f"Raw message: {raw_message}")
        logger.debug(f"Message body: {message_body}")
        
        try:
            discord_message = DiscordSQSMessage(message_body)
            logger.debug(f"Processing {discord_message.type} message for order {discord_message.order_id}")
            
            if discord_message.type in self.message_handlers:
                handler = self.message_handlers[discord_message.type]
                logger.debug(f"Calling handler for {discord_message.type}")
                
                start_time = asyncio.get_event_loop().time()
                result = await handler(discord_message)
                processing_time = asyncio.get_event_loop().time() - start_time
                
                if result:
                    logger.debug(f"Successfully processed {discord_message.type} message in {processing_time:.2f}s")
                else:
                    logger.error(f"Failed to process {discord_message.type} message in {processing_time:.2f}s")
                
                return result
            else:
                logger.warning(f"Unknown message type: {discord_message.type} - this may be a configuration issue")
                logger.debug(f"Available handlers: {list(self.message_handlers.keys())}")
                return False
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error processing message {message_id}: {e}")
            logger.error(f"Message body that failed to decode: {message_body}")
            return False
        except KeyError as e:
            logger.error(f"Missing required field in message {message_id}: {e}")
            logger.error(f"Message body: {message_body}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error processing Discord queue message {message_id}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Message body: {message_body}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    
    async def _handle_create_thread(self, message: DiscordSQSMessage) -> bool:
        """Handle create_thread message type"""
        try:
            payload = message.payload
            logger.debug(f"Processing create_thread payload: {payload}")
            
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
            
            logger.debug(f"Extracted fields: server_id={server_id}, channel_id={channel_id}, members={members}, entity_type={entity_type}, entity_id={entity_id}")
            logger.debug(f"Business entity ID for correlation: {business_entity_id} (from entity_id: {entity_id}, metadata order_id: {message.order_id})")
            
            # Validate required fields
            if not all([server_id, channel_id, members]):
                error_msg = f"Missing required fields for create_thread: server_id={server_id}, channel_id={channel_id}, members={members}"
                logger.error(error_msg)
                logger.error(f"Payload: {payload}")
                await self._send_error_response(message, error_msg)
                return False
            
            # Validate data types
            try:
                # Test if IDs can be converted to integers
                int(server_id)
                int(channel_id)
                [int(member) for member in members if member]
            except (ValueError, TypeError) as e:
                error_msg = f"Invalid ID format in create_thread: {e}"
                logger.error(error_msg)
                logger.error(f"Raw values: server_id={server_id}, channel_id={channel_id}, members={members}")
                await self._send_error_response(message, error_msg)
                return False
            
            # Create the thread using existing bot method
            logger.debug(f"Calling bot.order_placed with data: {{'server_id': {server_id}, 'channel_id': {channel_id}, 'members': {members}, 'order': {order}, 'customer_discord_id': {customer_discord_id}}}")
            
            start_time = asyncio.get_event_loop().time()
            result = await self.bot.order_placed({
                'server_id': server_id,
                'channel_id': channel_id,
                'members': members,
                'order': order,
                'customer_discord_id': customer_discord_id
            })
            processing_time = asyncio.get_event_loop().time() - start_time
            
            logger.debug(f"Thread creation result: {result} (took {processing_time:.2f}s)")
            
            if result and not result.get('failed'):
                # Get the newly created thread ID
                new_thread_id = result.get('thread', {}).get('thread_id')
                
                # CRITICAL FIX: Ensure we're sending the business entity ID, not the thread ID
                logger.debug(f"Sending response: thread_id={new_thread_id}, original_order_id={business_entity_id}")
                
                # Send success response
                response = DiscordSQSResponse(
                    'thread_created',
                    {
                        'thread_id': new_thread_id,
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
                logger.debug(f"Thread created successfully: {new_thread_id}")
                return True
            else:
                # Send error response
                error_msg = result.get('message', 'Unknown error') if result else 'No result returned'
                logger.error(f"Thread creation failed: {error_msg}")
                logger.error(f"Full result: {result}")
                await self._send_error_response(message, error_msg)
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error handling create_thread: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Message: {message}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
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
                logger.debug(f"Response sent successfully: {response.type}")
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
            
            logger.debug(f"Sending error response: original_order_id={business_entity_id}, error={error_message}")
            
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
        self.health_task = None
        self.restart_count = 0
        self.last_restart_time = 0
        self.consumer_start_time = 0
        
    async def initialize(self):
        """Initialize SQS client and consumer"""
        try:
            from util.sqs_client import SQSClient
            self.sqs_client = SQSClient()
            self.consumer = DiscordSQSConsumer(self.bot, self.sqs_client)
            
            if not self.sqs_client.sqs:
                logger.error("SQS client initialization failed")
                return False
                
            logger.debug("Discord SQS manager initialized successfully")
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
            
            # Start consumer with enhanced monitoring
            self.consumer_task = asyncio.create_task(
                self._run_consumer_with_monitoring(queue_name)
            )
            
            # Start health monitoring
            self.health_task = asyncio.create_task(self._comprehensive_health_monitor(queue_name))
            
            self.consumer_start_time = asyncio.get_event_loop().time()
            logger.debug(f"Started Discord SQS consumer for queue: {queue_name}")
            
        except Exception as e:
            logger.error(f"Failed to start Discord SQS consumer: {e}")
    
    async def _run_consumer_with_monitoring(self, queue_name: str):
        """Run the consumer with comprehensive monitoring and automatic restart"""
        try:
            logger.debug(f"Starting consumer for queue: {queue_name}")
            
            await self.sqs_client.start_consumer(
                queue_name,
                self.consumer.process_message,
                Config.SQS_CONSUMER_SETTINGS['max_messages'],
                Config.SQS_CONSUMER_SETTINGS['wait_time']
            )
            
        except asyncio.CancelledError:
            logger.info(f"Consumer for queue {queue_name} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Consumer for queue {queue_name} encountered fatal error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Attempt automatic restart
            await self._attempt_restart(queue_name, str(e))
    
    async def _attempt_restart(self, queue_name: str, error_reason: str):
        """Attempt to restart the consumer with backoff"""
        current_time = asyncio.get_event_loop().time()
        time_since_last_restart = current_time - self.last_restart_time
        
        # Implement exponential backoff
        if self.restart_count < 5:
            wait_time = min(30 * (2 ** self.restart_count), 300)  # Max 5 minutes
        else:
            wait_time = 300  # 5 minutes for subsequent restarts
        
        if time_since_last_restart < wait_time:
            logger.warning(f"Consumer restart attempted too soon. Waiting {wait_time - time_since_last_restart:.1f}s")
            await asyncio.sleep(wait_time - time_since_last_restart)
        
        self.restart_count += 1
        self.last_restart_time = current_time
        
        logger.warning(f"Attempting to restart consumer for queue {queue_name} (attempt {self.restart_count})")
        logger.warning(f"Previous error: {error_reason}")
        
        try:
            # Stop current consumer
            await self.stop_consumer()
            
            # Wait before restart
            await asyncio.sleep(5)
            
            # Restart consumer
            await self.start_consumer()
            
            logger.info(f"Successfully restarted consumer for queue {queue_name}")
            
        except Exception as e:
            logger.error(f"Failed to restart consumer for queue {queue_name}: {e}")
            
            # If restart fails, try again after a longer delay
            if self.restart_count < 10:
                logger.info(f"Scheduling another restart attempt in 60 seconds")
                await asyncio.sleep(60)
                await self._attempt_restart(queue_name, f"Restart failed: {e}")
            else:
                logger.error(f"Maximum restart attempts reached for queue {queue_name}. Manual intervention required.")
    
    async def _comprehensive_health_monitor(self, queue_name: str):
        """Comprehensive health monitoring for the consumer"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = asyncio.get_event_loop().time()
                uptime = current_time - self.consumer_start_time
                
                # Check consumer task status
                consumer_healthy = (
                    self.consumer_task and 
                    not self.consumer_task.done() and 
                    not self.consumer_task.cancelled()
                )
                
                # Get SQS client health
                sqs_health = self.sqs_client.get_health_status() if self.sqs_client else {}
                
                # Get queue attributes
                queue_attributes = await self.sqs_client.get_queue_attributes(queue_name) if self.sqs_client else {}
                
                # Log comprehensive health status
                logger.debug(f"Consumer health check - Queue: {queue_name}")
                logger.debug(f"  Consumer task: {'Healthy' if consumer_healthy else 'Unhealthy'}")
                logger.debug(f"  Uptime: {uptime:.1f}s")
                logger.debug(f"  Restart count: {self.restart_count}")
                logger.debug(f"  Last restart: {self.last_restart_time:.1f}s ago")
                
                if sqs_health:
                    logger.debug(f"  SQS client: {sqs_health.get('client_initialized', False)}")
                    logger.debug(f"  Last message: {sqs_health.get('time_since_last_message', 0):.1f}s ago")
                    logger.debug(f"  Total messages: {sqs_health.get('message_count', 0)}")
                    logger.debug(f"  Error count: {sqs_health.get('error_count', 0)}")
                
                if queue_attributes:
                    depth = int(queue_attributes.get('ApproximateNumberOfMessages', 0))
                    in_flight = int(queue_attributes.get('ApproximateNumberOfMessagesNotVisible', 0))
                    logger.debug(f"  Queue depth: {depth}, In flight: {in_flight}")
                
                # Check for unhealthy conditions
                if not consumer_healthy:
                    logger.error(f"Consumer task is unhealthy for queue {queue_name}")
                    await self._attempt_restart(queue_name, "Consumer task unhealthy")
                
                # Check for long periods without messages
                if sqs_health and sqs_health.get('time_since_last_message', 0) > 900:  # 15 minutes
                    logger.warning(f"Queue {queue_name} has not received messages for {sqs_health['time_since_last_message']:.1f} seconds")
                
                # Check for high error rates
                if sqs_health and sqs_health.get('error_count', 0) > 10:
                    logger.warning(f"Queue {queue_name} has high error count: {sqs_health['error_count']}")
                
                # Check for high queue depth
                if queue_attributes and int(queue_attributes.get('ApproximateNumberOfMessages', 0)) > 100:
                    logger.warning(f"Queue {queue_name} has high depth: {queue_attributes['ApproximateNumberOfMessages']} messages")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def stop_consumer(self):
        """Stop the Discord SQS consumer"""
        logger.debug("Stopping Discord SQS consumer...")
        
        # Cancel health monitoring
        if self.health_task and not self.health_task.done():
            self.health_task.cancel()
            try:
                await self.health_task
            except asyncio.CancelledError:
                pass
            self.health_task = None
        
        # Cancel consumer task
        if self.consumer_task and not self.consumer_task.done():
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass
        
        self.consumer_task = None
        logger.debug("Stopped Discord SQS consumer")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of the SQS manager"""
        current_time = asyncio.get_event_loop().time()
        
        return {
            'consumer_initialized': self.consumer is not None,
            'sqs_client_initialized': self.sqs_client is not None,
            'consumer_task_running': (
                self.consumer_task and 
                not self.consumer_task.done() and 
                not self.consumer_task.cancelled()
            ),
            'health_task_running': (
                self.health_task and 
                not self.health_task.done() and 
                not self.health_task.cancelled()
            ),
            'uptime': current_time - self.consumer_start_time if self.consumer_start_time else 0,
            'restart_count': self.restart_count,
            'last_restart': self.last_restart_time,
            'sqs_health': self.sqs_client.get_health_status() if self.sqs_client else None
        }
