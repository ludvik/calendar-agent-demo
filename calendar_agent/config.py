import os
import sqlite3
from pathlib import Path
from typing import Optional

import logfire
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .models import Base

# Setup base path
BASE_DIR = Path(__file__).parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")  # Load non-sensitive configs first
load_dotenv(BASE_DIR / ".env.secrets")  # Load sensitive configs (these will override)

# Setup logging
logger.remove()  # Remove default handler

# File logging - detailed logs
logger.add(
    "logs/calendar_agent.log",
    rotation="500 MB",
    retention="10 days",
    compression="zip",
    backtrace=True,
    diagnose=True,
    enqueue=True,
    catch=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    level="DEBUG",  # Log everything to file
)

# Console logging - only important messages
import sys

logger.add(
    sys.stderr,
    format="<level>{message}</level>",
    level="WARNING",  # Only warnings and errors to console
    backtrace=True,
    diagnose=True,
)


class DatabaseConfig:
    """Database configuration and initialization."""

    def __init__(self, db_url: Optional[str] = None):
        """Initialize database configuration.

        Args:
            db_url: Database URL. If None, uses environment variable or default SQLite.
        """
        self.db_url = db_url or os.getenv("DATABASE_URL", "sqlite:///calendar.db")
        self._engine = None
        self._session_factory = None

    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine."""
        if self._engine is None:
            connect_args = {}
            if self.db_url.startswith("sqlite"):
                # Enable SQLite to handle datetime types better
                connect_args["detect_types"] = (
                    sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
                )
                # Note: SQLite still doesn't fully support timezone-aware datetimes
                # We'll handle timezone conversion in the service layer

            self._engine = create_engine(
                self.db_url,
                connect_args=connect_args,
            )
            # Create tables if they don't exist
            Base.metadata.create_all(self._engine)
        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """Get or create SQLAlchemy session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def init_db(self) -> Engine:
        """Initialize the database and return the engine."""
        return self.engine


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
        # Disable Logfire console output via environment variable
        os.environ["LOGFIRE_CONSOLE_LOG"] = "false"

        # Configure logfire
        logfire.configure(
            service_name="calendar_agent",
        )
        # Enable HTTP request tracking
        logfire.instrument_httpx(capture_all=True)
        logger.debug("Logfire configured")

        # Database configuration
        self.db = DatabaseConfig()
        logger.debug(f"Database configured with URL: {self.db.db_url}")

        # Sensitive configurations
        self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")

        # Non-sensitive configurations - strip comments from env values
        def get_env_int(key: str, default: int) -> int:
            value = os.getenv(key, str(default))
            return int(value.split("#")[0].strip())

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").split("#")[0].strip()

        # Update log levels if specified in environment
        if self.log_level != "INFO":
            logger.remove()
            logger.add(
                "logs/calendar_agent.log",
                rotation="500 MB",
                retention="10 days",
                compression="zip",
                backtrace=True,
                diagnose=True,
                enqueue=True,
                catch=True,
                format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
                level=self.log_level,
            )
            logger.add(
                sys.stderr,
                format="<level>{message}</level>",
                level="WARNING",
                backtrace=True,
                diagnose=True,
            )

        # Flag to indicate if we're using a real LLM
        self.is_using_real_llm = bool(self.openai_api_key)


# Create global config instance
config = Config()
