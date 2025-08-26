import asyncio
import json
import logging
import os
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
                
            logger.info(f"SQS client initialized successfully in region {aws_region}")
            
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
            
            logger.info(f"Message sent to queue '{queue_name}' with ID: {response['MessageId']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to queue '{queue_name}': {e}")
            return False
    
    async def start_consumer(self, queue_name: str, message_handler: Callable, 
                            max_messages: int = 10, wait_time: int = 20):
        """Start consuming messages from an SQS queue"""
        if not self.sqs:
            logger.error("SQS client not initialized")
            return
            
        queue_url = self.get_queue_url(queue_name)
        if not queue_url:
            return
            
        logger.info(f"Starting SQS consumer for queue: {queue_name}")
        logger.info(f"Consumer settings: max_messages={max_messages}, wait_time={wait_time}s")
        
        try:
            while True:
                try:
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
                        logger.info(f"Received {len(messages)} messages from queue '{queue_name}'")
                        
                        # Process messages concurrently to avoid blocking
                        tasks = []
                        for message in messages:
                            task = asyncio.create_task(self._process_single_message(
                                message, message_handler, queue_url
                            ))
                            tasks.append(task)
                        
                        # Wait for all messages to be processed
                        if tasks:
                            await asyncio.gather(*tasks, return_exceptions=True)
                    # No logging for timeouts - this is normal behavior
                                
                except Exception as e:
                    logger.error(f"Error receiving messages from queue '{queue_name}': {e}")
                    await asyncio.sleep(5)  # Wait before retrying
        except asyncio.CancelledError:
            logger.info(f"SQS consumer for queue '{queue_name}' was cancelled")
        except Exception as e:
            logger.error(f"SQS consumer for queue '{queue_name}' encountered fatal error: {e}")
        finally:
            logger.info(f"SQS consumer for queue '{queue_name}' stopped")
    
    async def _process_single_message(self, message: Dict[str, Any], message_handler: Callable, queue_url: str):
        """Process a single SQS message"""
        message_id = message.get('MessageId', 'unknown')
        receipt_handle = message.get('ReceiptHandle', 'unknown')
        
        logger.info(f"Processing SQS message {message_id}")
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
            
            # Process message asynchronously
            start_time = asyncio.get_event_loop().time()
            result = await message_handler(body, message)
            processing_time = asyncio.get_event_loop().time() - start_time
            
            if result:
                logger.info(f"Successfully processed message {message_id} in {processing_time:.2f}s")
                
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
