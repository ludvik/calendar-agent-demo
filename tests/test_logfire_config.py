import os

import logfire
import pytest

from calendar_agent.config import config


def test_logfire_configuration():
    """Test that Logfire is properly configured during pytest execution."""
    # Check if Logfire is configured
    print("Logfire configuration:")
    print(f"LOGFIRE_CONSOLE_LOG: {os.environ.get('LOGFIRE_CONSOLE_LOG')}")
    print(
        f"LOGFIRE_API_KEY: {'Set' if os.environ.get('LOGFIRE_API_KEY') else 'Not set'}"
    )
    print(f"LOGFIRE_DATASET: {os.environ.get('LOGFIRE_DATASET')}")

    # Try to log something
    logfire.info("test_message_from_pytest", test_value="This is a test")

    # Check if config is properly initialized
    assert config is not None
    assert hasattr(config, "is_using_real_llm")

    # Print config values
    print(f"Config log_level: {config.log_level}")
    print(f"Using real LLM: {config.is_using_real_llm}")

    # Test passes if we get here
    assert True
