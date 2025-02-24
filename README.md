# Calendar Agent Demo

A demo project for an AI-powered calendar management system that helps real estate agents manage their schedules efficiently.

## Prerequisites

- Python 3.9 or higher
- Poetry for dependency management
- OpenAI API key (optional - will use test mode if not provided)

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/calendar-agent-demo.git
cd calendar-agent-demo
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Configure environment variables:
```bash
cp .env.secrets.example .env.secrets
```

Edit `.env.secrets` and set your configuration:
```env
# OpenAI API Configuration
OPENAI_API_KEY=your_api_key_here

# Logging Configuration
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

If you don't set up an API key, the system will run in test mode using mock responses. This is useful for development and testing, but won't provide real AI interactions.

## Running the Demo

Start the chat interface:
```bash
poetry run python run.py
```

The system will indicate whether it's using the real GPT-4 model or running in test mode. All interactions and errors are logged to `logs/calendar_agent.log`.

You can interact with the calendar agent using natural language queries like:
- "Am I free tomorrow at 2 PM?"
- "Find me a 30-minute slot between 2 PM and 5 PM tomorrow"
- "Is next Monday wide open?"

## Project Structure

```
calendar-agent-demo/
├── pyproject.toml          # Project configuration and dependencies
├── README.md              # This file
├── run.py                 # Entry point script
└── calendar_agent/        # Main package
    ├── __init__.py       # Package initialization
    ├── agent.py          # AI agent implementation
    ├── calendar_tool.py  # Calendar operations
    └── main.py           # Chat interface
```

## Development

The project uses Poetry for dependency management. Common commands:

- Add a new dependency:
```bash
poetry add package-name
```

- Add a development dependency:
```bash
poetry add --dev package-name
```

- Update dependencies:
```bash
poetry update
```

- Run tests:
```bash
poetry run pytest
```

## Notes

- Currently using a mock calendar implementation for demonstration
- Supports various LLM providers (OpenAI, Anthropic, Google)
- File-based storage for simplicity
