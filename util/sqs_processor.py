import asyncio
import logging
from typing import Dict, Any, Optional

from util.config import Config

logger = logging.getLogger('SCMarketBot.SQSProcessor')

class SQSMessageProcessor:
    """Processes SQS messages and routes them to appropriate bot methods"""
    
    def __init__(self, bot):
        self.bot = bot
        self.processors = {
            'order_placed': self._process_order_placed,
            'order_assigned': self._process_order_assigned,
            'order_status_updated': self._process_order_status_updated
        }
    
    async def process_message(self, message_body: Dict[str, Any], raw_message: Dict[str, Any]) -> bool:
        """Process an incoming SQS message"""
        try:
            event_type = message_body.get('event_type')
            data = message_body.get('data', {})
            timestamp = message_body.get('timestamp')
            
            logger.info(f"Processing {event_type} event from {timestamp}")
            
            if event_type in self.processors:
                processor = self.processors[event_type]
                result = await processor(data)
                
                if result:
                    logger.info(f"Successfully processed {event_type} event")
                else:
                    logger.error(f"Failed to process {event_type} event")
                
                return result
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False
    
    async def _process_order_placed(self, data: Dict[str, Any]) -> bool:
        """Process order placed event"""
        try:
            result = await self.bot.order_placed(data)
            
            if result and not result.get('failed'):
                logger.info(f"Order placed successfully: {result.get('thread', {}).get('thread_id')}")
                return True
            else:
                logger.error(f"Order placement failed: {result.get('message')}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing order placed: {e}")
            return False
    
    async def _process_order_assigned(self, data: Dict[str, Any]) -> bool:
        """Process order assigned event"""
        try:
            result = await self.bot.add_to_thread(
                data.get('server_id'),
                data.get('thread_id'),
                data.get('members'),
                data.get('order')
            )
            
            if result:
                logger.info(f"Order assigned successfully to thread {data.get('thread_id')}")
                return True
            else:
                logger.error("Order assignment failed")
                return False
                
        except Exception as e:
            logger.error(f"Error processing order assigned: {e}")
            return False
    
    async def _process_order_status_updated(self, data: Dict[str, Any]) -> bool:
        """Process order status updated event"""
        try:
            result = await self.bot.order_status_update(data.get('order'))
            
            if result:
                logger.info(f"Order status updated successfully")
                return True
            else:
                logger.error("Order status update failed")
                return False
                
        except Exception as e:
            logger.error(f"Error processing order status update: {e}")
            return False

class SQSManager:
    """Manages SQS consumers and message processing"""
    
    def __init__(self, bot):
        self.bot = bot
        self.sqs_client = None
        self.processor = None
        self.consumer_tasks = []
        
    async def initialize(self):
        """Initialize SQS client and processor"""
        try:
            from util.sqs_client import SQSClient
            self.sqs_client = SQSClient()
            self.processor = SQSMessageProcessor(self.bot)
            
            if not self.sqs_client.sqs:
                logger.error("SQS client initialization failed")
                return False
                
            logger.info("SQS manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize SQS manager: {e}")
            return False
    
    async def start_consumers(self):
        """Start SQS consumers for all configured queues"""
        if not self.sqs_client or not self.processor:
            logger.error("SQS manager not initialized")
            return
        
        try:
            # Start consumer for order placed queue
            order_placed_task = asyncio.create_task(
                self.sqs_client.start_consumer(
                    Config.get_sqs_queue_name('order_placed'),
                    self.processor.process_message,
                    Config.SQS_CONSUMER_SETTINGS['max_messages'],
                    Config.SQS_CONSUMER_SETTINGS['wait_time']
                )
            )
            self.consumer_tasks.append(order_placed_task)
            
            # Start consumer for order assigned queue
            order_assigned_task = asyncio.create_task(
                self.sqs_client.start_consumer(
                    Config.get_sqs_queue_name('order_assigned'),
                    self.processor.process_message,
                    Config.SQS_CONSUMER_SETTINGS['max_messages'],
                    Config.SQS_CONSUMER_SETTINGS['wait_time']
                )
            )
            self.consumer_tasks.append(order_assigned_task)
            
            # Start consumer for order status updated queue
            order_status_task = asyncio.create_task(
                self.sqs_client.start_consumer(
                    Config.get_sqs_queue_name('order_status_updated'),
                    self.processor.process_message,
                    Config.SQS_CONSUMER_SETTINGS['max_messages'],
                    Config.SQS_CONSUMER_SETTINGS['wait_time']
                )
            )
            self.consumer_tasks.append(order_status_task)
            
            logger.info(f"Started {len(self.consumer_tasks)} SQS consumers")
            
        except Exception as e:
            logger.error(f"Failed to start SQS consumers: {e}")
    
    async def stop_consumers(self):
        """Stop all SQS consumers"""
        for task in self.consumer_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.consumer_tasks.clear()
        logger.info("Stopped all SQS consumers")
    
    async def send_order_placed(self, order_data: Dict[str, Any]) -> bool:
        """Send order placed event to SQS"""
        if not self.sqs_client:
            return False
        return await self.sqs_client.send_order_placed(order_data)
    
    async def send_order_assigned(self, assignment_data: Dict[str, Any]) -> bool:
        """Send order assigned event to SQS"""
        if not self.sqs_client:
            return False
        return await self.sqs_client.send_order_assigned(assignment_data)
    
    async def send_order_status_updated(self, status_data: Dict[str, Any]) -> bool:
        """Send order status updated event to SQS"""
        if not self.sqs_client:
            return False
        return await self.sqs_client.send_order_status_updated(status_data)
