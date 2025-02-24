from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
import os

# Setup logging
logger.remove()  # Remove default handler
logger.add(
    "logs/calendar_agent.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)
logger.add(
    lambda msg: print(msg),  # Also log to console
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    level="INFO",
)

# Load environment variables
env_path = Path(__file__).parent.parent / '.env.secrets'
load_dotenv(env_path)


class Config:
    """Global configuration singleton"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize configuration"""
        self.openai_api_key: Optional[str] = os.getenv('OPENAI_API_KEY')
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')
        
        # Update log levels if specified in environment
        if self.log_level != 'INFO':
            logger.remove()
            logger.add(
                "logs/calendar_agent.log",
                level=self.log_level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            )
            logger.add(
                lambda msg: print(msg),
                colorize=True,
                format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
                level=self.log_level,
            )

    @property
    def is_using_real_llm(self) -> bool:
        """Check if we're using a real LLM or test mode"""
        return bool(self.openai_api_key)


# Create global config instance
config = Config()
