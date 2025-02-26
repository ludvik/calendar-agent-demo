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

## Testing

The project uses pytest for testing. To run the tests:

```bash
# Run all tests
poetry run pytest

# Run tests with verbose output
poetry run pytest -v

```

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


## Technology Choices
### AI & Agent Framework
- **pydantic-ai**: Core framework for building AI agents
  - Agent definition and tool integration
  - Type-safe prompt engineering
  - Response validation and parsing

### Logging & Monitoring
- **Pydantic Logfire**: Advanced monitoring and observability
  - Real-time agent behavior tracking
  - API request/response logging
  - Performance metrics
  - Error tracking