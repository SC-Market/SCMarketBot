import json
import logging
import os
import re
import sys
from datetime import datetime, timezone


# Secrets that must never reach the logs, even inside an exception message.
_SCRUBBERS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.I), r"\1[REDACTED]"),
    # Discord bot tokens.
    (re.compile(r"\b[MNO][A-Za-z\d_-]{23,27}\.[\w-]{6}\.[\w-]{27,}"), "[REDACTED]"),
    # JWTs.
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), "[REDACTED]"),
    # Secret query parameters.
    (
        re.compile(r"([?&](?:code|token|access_token|refresh_token|secret|password)=)[^&\s\"']+", re.I),
        r"\1[REDACTED]",
    ),
]


def scrub(text: str) -> str:
    for pattern, replacement in _SCRUBBERS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so Lightsail keeps a log call (traceback
    included) as a single event. The message text is unchanged, so
    `--filter-pattern command_used` still matches."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "msg": scrub(record.getMessage()),
            "logger": record.name,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            exc_type, exc, _ = record.exc_info
            entry["error"] = {
                "name": exc_type.__name__ if exc_type else "Exception",
                "message": scrub(str(exc)),
                "stack": scrub(self.formatException(record.exc_info)),
            }
        if record.stack_info:
            entry["stack_info"] = scrub(record.stack_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def use_json_logs() -> bool:
    """JSON lines unless LOG_FORMAT=text, or stdout is a terminal (local dev).
    In the container stdout is not a TTY, so production gets JSON with no
    env change."""
    fmt = (os.environ.get("LOG_FORMAT") or "").strip().lower()
    if fmt in ("json", "text"):
        return fmt == "json"
    return not sys.stdout.isatty()


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
        console_handler.setFormatter(JsonFormatter() if use_json_logs() else formatter)
        
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
