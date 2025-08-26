import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any

class LoggingConfig:
    """Centralized logging configuration for the SCMarket bot"""
    
    # Log levels for different components
    COMPONENT_LEVELS = {
        'SCMarketBot': 'INFO',  # Main bot logger
        'SCMarketBot.DiscordSQSConsumer': 'INFO',  # SQS consumer
        'SCMarketBot.SQS': 'INFO',  # SQS client
        'SCMarketBot.SQSProcessor': 'INFO',  # SQS processor
        'SCMarketBot.Fetch': 'DEBUG',  # HTTP fetch utilities
        'SCMarketBot.OrderCog': 'INFO',  # Order cog
        'SCMarketBot.StockCog': 'INFO',  # Stock cog
        'discord': 'WARNING',  # Discord.py library
        'aiohttp': 'WARNING',  # aiohttp library
        'boto3': 'WARNING',  # AWS SDK
        'botocore': 'WARNING',  # AWS SDK core
    }
    
    @classmethod
    def setup_logging(cls, log_level: str = None) -> logging.Logger:
        """Setup comprehensive logging for the bot"""
        
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Create formatter with timestamp, logger name, log level, function name, and line number
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler - INFO level by default
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # File handler for errors only
        error_handler = logging.FileHandler('logs/error.log')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        
        # File handler for all logs
        all_handler = logging.FileHandler('logs/bot.log')
        all_handler.setLevel(logging.DEBUG)
        all_handler.setFormatter(formatter)
        
        # File handler for SQS-specific logs
        sqs_handler = logging.FileHandler('logs/sqs.log')
        sqs_handler.setLevel(logging.DEBUG)
        sqs_handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(all_handler)
        
        # Configure component-specific loggers
        for component, level in cls.COMPONENT_LEVELS.items():
            logger = logging.getLogger(component)
            logger.setLevel(getattr(logging, level.upper()))
            
            # Add SQS-specific handler for SQS components
            if 'SQS' in component:
                logger.addHandler(sqs_handler)
        
        # Get the main bot logger
        bot_logger = logging.getLogger('SCMarketBot')
        bot_logger.setLevel(logging.INFO)
        
        # Log the logging setup
        bot_logger.info("Logging system initialized successfully")
        bot_logger.info(f"Log files: logs/bot.log, logs/error.log, logs/sqs.log")
        bot_logger.info(f"Console level: INFO, File level: DEBUG")
        
        return bot_logger
    
    @classmethod
    def set_component_level(cls, component: str, level: str):
        """Set the logging level for a specific component"""
        if level.upper() not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError(f"Invalid log level: {level}")
        
        logger = logging.getLogger(component)
        logger.setLevel(getattr(logging, level.upper()))
        
        # Update the component levels dict
        cls.COMPONENT_LEVELS[component] = level
        
        # Log the change
        main_logger = logging.getLogger('SCMarketBot')
        main_logger.info(f"Set logging level for {component} to {level}")
    
    @classmethod
    def get_component_levels(cls) -> Dict[str, str]:
        """Get current logging levels for all components"""
        return cls.COMPONENT_LEVELS.copy()
    
    @classmethod
    def log_startup_info(cls):
        """Log startup information including configuration"""
        logger = logging.getLogger('SCMarketBot')
        
        logger.info("=" * 60)
        logger.info("SCMarket Bot Starting Up")
        logger.info("=" * 60)
        logger.info(f"Startup time: {datetime.now().isoformat()}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Log files directory: {os.path.abspath('logs')}")
        logger.info("=" * 60)
        
        # Log component levels
        logger.info("Component logging levels:")
        for component, level in cls.COMPONENT_LEVELS.items():
            logger.info(f"  {component}: {level}")
        logger.info("=" * 60)
    
    @classmethod
    def log_shutdown_info(cls):
        """Log shutdown information"""
        logger = logging.getLogger('SCMarketBot')
        
        logger.info("=" * 60)
        logger.info("SCMarket Bot Shutting Down")
        logger.info("=" * 60)
        logger.info(f"Shutdown time: {datetime.now().isoformat()}")
        logger.info("=" * 60)
    
    @classmethod
    def create_rotating_handlers(cls):
        """Create rotating file handlers for better log management"""
        try:
            from logging.handlers import RotatingFileHandler
            
            # Rotating handler for main bot log
            rotating_bot_handler = RotatingFileHandler(
                'logs/bot.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            rotating_bot_handler.setLevel(logging.DEBUG)
            rotating_bot_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')
            )
            
            # Rotating handler for error log
            rotating_error_handler = RotatingFileHandler(
                'logs/error.log',
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            rotating_error_handler.setLevel(logging.ERROR)
            rotating_error_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')
            )
            
            # Rotating handler for SQS log
            rotating_sqs_handler = RotatingFileHandler(
                'logs/sqs.log',
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            rotating_sqs_handler.setLevel(logging.DEBUG)
            rotating_sqs_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')
            )
            
            return rotating_bot_handler, rotating_error_handler, rotating_sqs_handler
            
        except ImportError:
            # Fallback to regular handlers if rotating handlers not available
            return None, None, None
