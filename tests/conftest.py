"""
Pytest configuration file for the calendar-agent-demo project.
This file sets up fixtures and configurations for testing.
"""

import os
from pathlib import Path

import logfire
import pytest
from dotenv import load_dotenv

# Load environment variables from .env and .env.secrets
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.secrets")


@pytest.fixture(scope="session", autouse=True)
def setup_logfire():
    """
    Set up Logfire for testing.
    This fixture runs automatically before any tests.
    """
    # Configure Logfire for testing with local auth
    # No need to specify token as you're using logfire auth for local login
    logfire.configure(
        service_name="calendar_agent_test",
        console=logfire.ConsoleOptions(),  # Use default console options
        send_to_logfire=True,  # Explicitly enable sending logs to Logfire cloud
    )

    # Log test session start
    logfire.info("pytest_session_start", message="Starting test session")

    yield

    # Log test session end
    logfire.info("pytest_session_end", message="Test session completed")

    # Ensure all logs are sent before the test session ends
    logfire.force_flush()
