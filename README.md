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


## Running the Demo

Start the chat interface:
```bash
poetry run python -m calendar_agent.main
```

The system will indicate whether it's using the real GPT-4 model or running in test mode. All interactions are logged to:
- Console: Only warnings and errors for cleaner output
- Local file: `logs/calendar_agent.log` (detailed debug information)
- Logfire dashboard (if configured)

## Logfire Configuration and Usage

[Logfire](https://logfire.dev/) is an observability platform that helps monitor and debug agent <--> interactions.

### Setting up Logfire

1. Install the Logfire CLI if you haven't already:
```bash
pip install logfire
```

2. Authenticate with Logfire using the CLI:
```bash
logfire auth
```
This will open a browser window for you to log in to your Logfire account.

3. (Optional) Configure additional Logfire settings in `.env`:
```env
# Logfire Configuration
LOGFIRE_CONSOLE_LOG=false  # Set to true to enable Logfire console output
```

### Using Logfire

Once authenticated, the Calendar Agent Demo will automatically send logs to your Logfire dashboard. This includes:

- Application events and errors
- HTTP request tracking (enabled by default)
- Performance metrics

To view your logs:
1. Log in to your Logfire dashboard
2. Navigate to the "Logs" section
3. Filter by service name "calendar_agent"

You can also use the CLI to view logs:
```bash
logfire logs --service calendar_agent
```

### Disabling Logfire

If you don't want to use Logfire, you can log out using the CLI:
```bash
logfire logout
```

The application will fall back to local logging only when not authenticated with Logfire.
