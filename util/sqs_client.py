import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional, Callable

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import traceback

logger = logging.getLogger('SCMarketBot.SQS')

class SQSClient:
    def __init__(self):
        self.sqs = None
        self.queues = {}
        self.consumers = {}
        self._init_client()
        self.last_message_time = time.time()
        self.message_count = 0
        self.error_count = 0
        
    def _init_client(self):
        """Initialize the SQS client with AWS credentials"""
        try:
            # Try to get credentials from environment variables
            aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
            aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
            aws_region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
            
            if aws_access_key and aws_secret_key:
                self.sqs = boto3.client(
                    'sqs',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
            else:
                # Try to use IAM roles or default credentials
                self.sqs = boto3.client('sqs', region_name=aws_region)
                
            logger.debug(f"SQS client initialized successfully in region {aws_region}")
            
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            self.sqs = None
        except Exception as e:
            logger.error(f"Failed to initialize SQS client: {e}")
            self.sqs = None
    
    def get_queue_url(self, queue_name: str) -> Optional[str]:
        """Get the URL for a queue by name"""
        if not self.sqs:
            return None
            
        try:
            response = self.sqs.get_queue_url(QueueName=queue_name)
            return response['QueueUrl']
        except ClientError as e:
            if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                logger.error(f"Queue '{queue_name}' does not exist")
            else:
                logger.error(f"Error getting queue URL for '{queue_name}': {e}")
            return None
    
    async def get_queue_attributes(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """Get queue attributes including depth and other metrics"""
        if not self.sqs:
            return None
            
        try:
            queue_url = self.get_queue_url(queue_name)
            if not queue_url:
                return None
                
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sqs.get_queue_attributes(
                    QueueUrl=queue_url,
                    AttributeNames=['All']
                )
            )
            
            return response.get('Attributes', {})
            
        except Exception as e:
            logger.error(f"Failed to get queue attributes for '{queue_name}': {e}")
            return None
    
    async def send_message(self, queue_name: str, message_body: Dict[str, Any], 
                          message_attributes: Optional[Dict[str, Any]] = None) -> bool:
        """Send a message to an SQS queue"""
        if not self.sqs:
            logger.error("SQS client not initialized")
            return False
            
        try:
            queue_url = self.get_queue_url(queue_name)
            if not queue_url:
                return False
                
            message_attrs = {}
            if message_attributes:
                for key, value in message_attributes.items():
                    if isinstance(value, str):
                        message_attrs[key] = {
                            'StringValue': value,
                            'DataType': 'String'
                        }
                    elif isinstance(value, (int, float)):
                        message_attrs[key] = {
                            'StringValue': str(value),
                            'DataType': 'Number'
                        }
            
            # Use thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(message_body),
                    MessageAttributes=message_attrs
                )
            )
            
            logger.debug(f"Message sent to queue '{queue_name}' with ID: {response['MessageId']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to queue '{queue_name}': {e}")
            return False
    
    async def start_consumer(self, queue_name: str, message_handler: Callable, 
                            max_messages: int = 10, wait_time: int = 20):
        """Start consuming messages from an SQS queue with enhanced monitoring"""
        if not self.sqs:
            logger.error("SQS client not initialized")
            return
            
        queue_url = self.get_queue_url(queue_name)
        if not queue_url:
            return
            
        logger.debug(f"Starting SQS consumer for queue: {queue_name}")
        logger.debug(f"Consumer settings: max_messages={max_messages}, wait_time={wait_time}s")
        
        # Start health monitoring
        health_task = asyncio.create_task(self._health_monitor(queue_name))
        
        try:
            while True:
                try:
                    # Log queue depth periodically
                    await self._log_queue_status(queue_name)
                    
                    # Use asyncio.to_thread to run boto3 calls in a thread pool
                    # This prevents blocking the main event loop
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.sqs.receive_message(
                            QueueUrl=queue_url,
                            MaxNumberOfMessages=max_messages,
                            WaitTimeSeconds=wait_time,
                            MessageAttributeNames=['All']
                        )
                    )
                    
                    messages = response.get('Messages', [])
                    if messages:
                        self.last_message_time = time.time()
                        self.message_count += len(messages)
                        logger.debug(f"Received {len(messages)} messages from queue '{queue_name}' (total: {self.message_count})")
                        
                        # Process messages concurrently to avoid blocking
                        tasks = []
                        for message in messages:
                            task = asyncio.create_task(self._process_single_message(
                                message, message_handler, queue_url
                            ))
                            tasks.append(task)
                        
                        # Wait for all messages to be processed with timeout
                        if tasks:
                            try:
                                await asyncio.wait_for(
                                    asyncio.gather(*tasks, return_exceptions=True),
                                    timeout=60  # 1 minute timeout for message processing
                                )
                            except asyncio.TimeoutError:
                                logger.error(f"Message processing timed out for {len(tasks)} messages")
                                # Cancel any remaining tasks
                                for task in tasks:
                                    if not task.done():
                                        task.cancel()
                    else:
                        # Log when no messages are received (but not too frequently)
                        current_time = time.time()
                        if current_time - self.last_message_time > 300:  # 5 minutes
                            logger.debug(f"No messages received from queue '{queue_name}' in the last 5 minutes")
                                
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"Error receiving messages from queue '{queue_name}': {e}")
                    logger.error(f"Error count: {self.error_count}")
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except asyncio.CancelledError:
            logger.debug(f"SQS consumer for queue '{queue_name}' was cancelled")
        except Exception as e:
            logger.error(f"SQS consumer for queue '{queue_name}' encountered fatal error: {e}")
        finally:
            # Cancel health monitoring
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass
            logger.debug(f"SQS consumer for queue '{queue_name}' stopped")
    
    async def _health_monitor(self, queue_name: str):
        """Monitor consumer health and log status"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = time.time()
                time_since_last_message = current_time - self.last_message_time
                
                # Get queue attributes
                attributes = await self.get_queue_attributes(queue_name)
                if attributes:
                    depth = int(attributes.get('ApproximateNumberOfMessages', 0))
                    in_flight = int(attributes.get('ApproximateNumberOfMessagesNotVisible', 0))
                    
                    logger.debug(f"Queue '{queue_name}' health: depth={depth}, in_flight={in_flight}, "
                              f"last_message={time_since_last_message:.1f}s ago, "
                              f"total_messages={self.message_count}, errors={self.error_count}")
                    
                    # Alert if no messages for too long
                    if time_since_last_message > 600:  # 10 minutes
                        logger.warning(f"Queue '{queue_name}' has not received messages for {time_since_last_message:.1f} seconds")
                    
                    # Alert if queue depth is high
                    if depth > 100:
                        logger.warning(f"Queue '{queue_name}' has high depth: {depth} messages")
                        
                else:
                    logger.warning(f"Could not get queue attributes for '{queue_name}'")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _log_queue_status(self, queue_name: str):
        """Log queue status periodically"""
        try:
            attributes = await self.get_queue_attributes(queue_name)
            if attributes:
                depth = int(attributes.get('ApproximateNumberOfMessages', 0))
                in_flight = int(attributes.get('ApproximateNumberOfMessagesNotVisible', 0))
                
                # Log queue depth every 5 minutes
                current_time = time.time()
                if not hasattr(self, '_last_queue_log') or current_time - getattr(self, '_last_queue_log', 0) > 300:
                    logger.debug(f"Queue '{queue_name}' status: depth={depth}, in_flight={in_flight}")
                    self._last_queue_log = current_time
                    
        except Exception as e:
            logger.debug(f"Could not log queue status: {e}")
    
    async def _process_single_message(self, message: Dict[str, Any], message_handler: Callable, queue_url: str):
        """Process a single SQS message with timeout protection"""
        message_id = message.get('MessageId', 'unknown')
        receipt_handle = message.get('ReceiptHandle', 'unknown')
        
        logger.debug(f"Processing SQS message {message_id}")
        logger.debug(f"Message details: {message}")
        
        try:
            # Parse message body
            try:
                body = json.loads(message['Body'])
                logger.debug(f"Parsed message body: {body}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON for message {message_id}: {e}")
                logger.error(f"Raw message body: {message.get('Body', 'No body')}")
                # Don't delete the message so it can be retried
                return
            
            # Process message asynchronously with timeout
            start_time = asyncio.get_event_loop().time()
            try:
                result = await asyncio.wait_for(
                    message_handler(body, message),
                    timeout=30  # 30 second timeout for message processing
                )
                processing_time = asyncio.get_event_loop().time() - start_time
                
                if result:
                    logger.debug(f"Successfully processed message {message_id} in {processing_time:.2f}s")
                    
                    # Delete message after successful processing using thread pool
                    try:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: self.sqs.delete_message(
                                QueueUrl=queue_url,
                                ReceiptHandle=receipt_handle
                            )
                        )
                        logger.debug(f"Deleted message {message_id} from queue")
                    except Exception as e:
                        logger.error(f"Failed to delete message {message_id} from queue: {e}")
                        logger.error(f"Error type: {type(e).__name__}")
                        # This is a critical error - we don't want to reprocess the message
                        logger.error(f"Full traceback: {traceback.format_exc()}")
                else:
                    logger.error(f"Message handler returned False for message {message_id} in {processing_time:.2f}s")
                    # Don't delete the message so it can be retried
                    
            except asyncio.TimeoutError:
                logger.error(f"Message processing timed out for message {message_id}")
                # Don't delete the message so it can be retried
                
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Message: {message}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Don't delete the message so it can be retried
    
    async def send_order_placed(self, order_data: Dict[str, Any]) -> bool:
        """Send order placed event to SQS"""
        return await self.send_message(
            'order-placed-queue',
            {
                'event_type': 'order_placed',
                'data': order_data,
                'timestamp': asyncio.get_event_loop().time()
            }
        )
    
    async def send_order_assigned(self, assignment_data: Dict[str, Any]) -> bool:
        """Send order assigned event to SQS"""
        return await self.send_message(
            'order-assigned-queue',
            {
                'event_type': 'order_assigned',
                'data': assignment_data,
                'timestamp': asyncio.get_event_loop().time()
            }
        )
    
    async def send_order_status_updated(self, status_data: Dict[str, Any]) -> bool:
        """Send order status updated event to SQS"""
        return await self.send_message(
            'order-status-updated-queue',
            {
                'event_type': 'order_status_updated',
                'data': status_data,
                'timestamp': asyncio.get_event_loop().time()
            }
        )

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of the SQS client"""
        current_time = time.time()
        return {
            'last_message_time': self.last_message_time,
            'time_since_last_message': current_time - self.last_message_time,
            'message_count': self.message_count,
            'error_count': self.error_count,
            'client_initialized': self.sqs is not None
        }
