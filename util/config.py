import os
from typing import Dict, Any

class Config:
    """Configuration class for the SCMarket bot"""
    
    # Discord settings
    DISCORD_API_KEY = os.environ.get("DISCORD_API_KEY")
    DISCORD_BACKEND_URL = os.environ.get("DISCORD_BACKEND_URL", "http://web:8081")
    
    # AWS SQS settings
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    
    # SQS Queue URLs (from deployed CDK stack)
    DISCORD_QUEUE_URL = os.environ.get('DISCORD_QUEUE_URL', 'https://sqs.us-east-2.amazonaws.com/272095582125/DiscordQueuesStack-discord-queue')
    BACKEND_QUEUE_URL = os.environ.get('BACKEND_QUEUE_URL', 'https://sqs.us-east-2.amazonaws.com/272095582125/DiscordQueuesStack-backend-queue')
    
    # Legacy SQS Queue names (for backward compatibility)
    SQS_QUEUES = {
        'order_placed': os.environ.get('SQS_ORDER_PLACED_QUEUE', 'order-placed-queue'),
        'order_assigned': os.environ.get('SQS_ORDER_ASSIGNED_QUEUE', 'order-assigned-queue'),
        'order_status_updated': os.environ.get('SQS_ORDER_STATUS_UPDATED_QUEUE', 'order-status-updated-queue')
    }
    
    # SQS Consumer settings
    SQS_CONSUMER_SETTINGS = {
        'max_messages': int(os.environ.get('SQS_MAX_MESSAGES', '10')),
        'wait_time': int(os.environ.get('SQS_WAIT_TIME', '20')),
        'retry_delay': int(os.environ.get('SQS_RETRY_DELAY', '5'))
    }
    
    # Web server settings
    WEB_SERVER_HOST = os.environ.get('WEB_SERVER_HOST', '0.0.0.0')
    WEB_SERVER_PORT = int(os.environ.get('WEB_SERVER_PORT', '8080'))
    
    # Feature flags
    ENABLE_SQS = os.environ.get('ENABLE_SQS', 'true').lower() == 'true'
    ENABLE_WEB_SERVER = os.environ.get('ENABLE_WEB_SERVER', 'true').lower() == 'true'
    ENABLE_DISCORD_QUEUE = os.environ.get('ENABLE_DISCORD_QUEUE', 'true').lower() == 'true'
    
    @classmethod
    def validate(cls) -> Dict[str, Any]:
        """Validate configuration and return any issues"""
        issues = {}
        
        if not cls.DISCORD_API_KEY:
            issues['DISCORD_API_KEY'] = 'Discord API key is required'
        
        if cls.ENABLE_SQS:
            if not cls.AWS_ACCESS_KEY_ID or not cls.AWS_SECRET_ACCESS_KEY:
                issues['AWS_CREDENTIALS'] = 'AWS credentials are required when SQS is enabled'
        
        return issues
    
    @classmethod
    def get_sqs_queue_name(cls, queue_type: str) -> str:
        """Get the SQS queue name for a specific type"""
        return cls.SQS_QUEUES.get(queue_type, f'{queue_type}-queue')
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment"""
        return os.environ.get('ENVIRONMENT', 'development').lower() == 'production'
