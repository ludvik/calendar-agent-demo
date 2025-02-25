# Calendar Agent Demo

A demo project for an AI-powered calendar management system that helps real estate agents manage their schedules efficiently.

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

3. Configure environment:

First, copy the example configuration files:
```bash
cp .env.example .env
cp .env.secrets.example .env.secrets
```

Edit `.env` for application settings:
```env
# Logging Configuration
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

Edit `.env.secrets` for sensitive information:
```env
# OpenAI API Configuration
OPENAI_API_KEY=your_api_key_here
```

If you don't set up an API key, the system will run in test mode using mock responses. This is useful for development and testing, but won't provide real AI interactions.

4. Configure Logfire (Optional):

The project uses [Pydantic Logfire](https://logfire.pydantic.dev/) for advanced monitoring and debugging. To set it up:

```bash
# Authenticate with Logfire
poetry run logfire auth

# Create a new project
poetry run logfire projects new
```

Once configured, you can monitor your agent's behavior, including:
- Agent runs and tool calls
- LLM API requests and responses
- Performance metrics
- Error tracking

Visit https://logfire.pydantic.dev to view your logs and metrics.

## Running the Demo

Start the chat interface:
```bash
poetry run python -m calendar_agent.main
```

The system will indicate whether it's using the real GPT-4 model or running in test mode. All interactions are logged to:
- Console: Only warnings and errors for cleaner output
- Local file: `logs/calendar_agent.log` (detailed debug information)
- Logfire dashboard (if configured)

You can interact with the calendar agent using natural language queries. The agent provides two types of responses:

1. Simple responses (for greetings and general questions):
   - "Hi"
   - "How can you help me?"

2. Calendar-specific responses (for scheduling and availability):
   - "Am I free tomorrow at 2 PM?"
   - "Find me a 30-minute slot between 2 PM and 5 PM tomorrow"
   - "Is next Monday wide open?"

## Project Structure

```
calendar-agent-demo/
├── pyproject.toml          # Project configuration and dependencies
├── README.md              # This file
├── .env                   # Application configuration
├── .env.secrets          # Sensitive configuration (API keys)
├── logs/                 # Log files directory
└── calendar_agent/        # Main package
    ├── __init__.py       # Package initialization
    ├── agent.py          # AI agent implementation with response types
    ├── calendar_tool.py  # Calendar operations
    ├── config.py         # Configuration management
    └── main.py           # Chat interface

## Monitoring and Debugging

The application uses a multi-level logging strategy:

1. Console Output:
   - Only shows warnings and errors
   - Keeps the interface clean for user interaction
   - Shows agent responses and calendar information

2. Log File (`logs/calendar_agent.log`):
   - Contains detailed debug information
   - Records all agent runs and tool calls
   - Logs API requests and responses
   - Stores error traces and stack information

3. Logfire Dashboard:
   - Real-time monitoring of agent behavior
   - Performance metrics and error tracking
   - Request/response logging
   - Tool usage analytics


## Tech Stack

### Core Dependencies
- **Poetry**: Modern dependency management and packaging
- **OpenAI GPT-4**: Large language model for natural language understanding

### AI & Agent Framework
- **pydantic-ai**: Core framework for building AI agents
  - Agent definition and tool integration
  - Type-safe prompt engineering
  - Response validation and parsing

### Data Validation & Settings
- **Pydantic**: Data validation using Python type annotations
  - Request/response model definitions
  - Configuration management
  - Type safety across the application

### Logging & Monitoring
- **Loguru**: Modern logging with structured output
  - Rotation and retention policies
  - Colored console output
  - Contextual logging

- **Pydantic Logfire**: Advanced monitoring and observability
  - Real-time agent behavior tracking
  - API request/response logging
  - Performance metrics
  - Error tracking