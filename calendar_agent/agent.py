import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Literal, Optional, Union

import logfire
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, models

from .calendar_tool import CalendarService, CalendarTool, TimeSlot
from .config import config
from .response import BaseResponse, CalendarResponse, ResponseType


class Message(BaseModel):
    """Message in conversation history"""

    role: str
    content: str


class CalendarDependencies(BaseModel):
    """Dependencies for calendar agent"""

    calendar: CalendarTool
    conversation_history: List[Message]

    model_config = {"arbitrary_types_allowed": True}


class ResponseType(str, Enum):
    """Type of response from the agent."""

    BASE = "BASE"
    CALENDAR = "CALENDAR"


class BaseResponse(BaseModel):
    """Base response for simple interactions that don't require calendar operations"""

    type: Literal[ResponseType.BASE] = ResponseType.BASE
    message: str = Field(description="Natural language response to the user")


class CalendarResponse(BaseModel):
    """Response type for calendar-specific operations"""

    type: Literal[ResponseType.CALENDAR] = ResponseType.CALENDAR
    message: str = Field(description="Natural language response to the user")
    suggested_slots: Optional[List[TimeSlot]] = Field(
        default=None, description="List of suggested time slots if applicable"
    )
    action_taken: Optional[str] = Field(
        default=None, description="Description of any actions taken"
    )


def get_conversation_context(history: List[Message]) -> str:
    """Convert conversation history to a string context"""
    if not history:
        return "No previous context."

    context = "Previous conversation:\n"
    for msg in history[-5:]:  # Only use last 5 messages to avoid context length issues
        if msg.role == "user":
            context += f"User: {msg.content}\n"
        else:
            context += f"Assistant: {msg.content}\n"
    return context


def get_system_prompt(history: List[Message]) -> str:
    """Get system prompt with current time and conversation history"""
    current_time = datetime.now()
    conversation_context = get_conversation_context(history)

    return f"""
    You are a helpful calendar assistant for a real estate agent.
    Your job is to help manage their schedule efficiently.
    Always be professional and concise in your responses.

    CURRENT TIME: {current_time.strftime('%Y-%m-%d %I:%M %p %Z')}
    When users mention relative times like "tomorrow" or "next Monday",
    calculate them relative to the current time shown above.

    CONVERSATION CONTEXT:
    {conversation_context}

    For simple interactions like greetings or general questions,
    return a BaseResponse with type="base" and just a message.
    Example: {{"type": "base", "message": "Hello! How can I help you today?"}}

    For calendar operations, ALWAYS use CalendarResponse with type="calendar".
    Include the following information:
    1. A natural language message describing what was done
    2. The specific action taken (e.g., "Scheduled meeting with John")
    3. For appointments:
       - Title, date, and time in a clear format (e.g., "2:00 PM")
       - Duration
       - Any other relevant details
    4. For availability checks:
       - Whether the time is available
       - If not available, what's blocking it
    5. For time slot suggestions:
       - List of available slots in a clear format
       - Any constraints considered (e.g., business hours)

    Example calendar responses:
    1. Scheduling:
    {{
        "type": "calendar",
        "message": "I've scheduled your meeting with John for tomorrow, February 26, at 2:00 PM for 1 hour.",
        "action_taken": "Scheduled: Meeting with John",
        "suggested_slots": null
    }}

    2. Availability check:
    {{
        "type": "calendar",
        "message": "I'm sorry, but you're not available at 2:00 PM tomorrow. You have a meeting with Sarah from 2:00 PM to 3:00 PM.",
        "action_taken": "Checked availability for 2:00 PM",
        "suggested_slots": null
    }}

    3. Finding slots:
    {{
        "type": "calendar",
        "message": "I found several available time slots tomorrow afternoon:\n1. 12:00 PM - 1:00 PM\n2. 1:00 PM - 2:00 PM\n3. 3:00 PM - 4:00 PM",
        "action_taken": "Found available slots",
        "suggested_slots": [...]
    }}
    """


# Configure LLM based on settings
if config.is_using_real_llm:
    models.ALLOW_MODEL_REQUESTS = True
    logger.info("Using OpenAI GPT-4 model")
else:
    logger.warning("No OpenAI API key found. Using test model (mock responses)")


calendar_agent = Agent(
    "openai:gpt-4",  # You can change this to your preferred model
    deps_type=CalendarDependencies,
    result_type=Union[BaseResponse, CalendarResponse],
    system_prompt=get_system_prompt([]),  # Start with empty history
)


@calendar_agent.tool
async def check_availability(
    ctx: RunContext[CalendarDependencies], time: datetime, duration: int = 60
) -> CalendarResponse:
    """Check if a specific time is available.

    Args:
        time: Time to check
        duration: Duration in minutes (default: 60)
        ctx: Agent context

    Returns:
        CalendarResponse: Response with availability info
    """
    if not ctx:
        raise ValueError("Context required")

    # Calculate end time
    end_time = time + timedelta(minutes=duration)

    # Check availability
    is_available = ctx.deps.calendar.check_availability(time, end_time)

    # Format response
    formatted_time = time.strftime("%I:%M %p").lstrip("0")  # Remove leading zero
    formatted_duration = f"{duration} minutes" if duration != 60 else "1 hour"

    if is_available:
        return CalendarResponse(
            type=ResponseType.CALENDAR,
            message=f"The time slot at {formatted_time} for {formatted_duration} is available.",
            action_taken=f"Checked availability for {formatted_time}",
            suggested_slots=None,
        )
    else:
        return CalendarResponse(
            type=ResponseType.CALENDAR,
            message=f"Sorry, the time slot at {formatted_time} for {formatted_duration} is not available.",
            action_taken=f"Checked availability for {formatted_time}",
            suggested_slots=None,
        )


@calendar_agent.tool
async def find_available_time_slots(
    ctx: RunContext[CalendarDependencies],
    start_time: datetime,
    end_time: datetime,
    duration: int = 60,
    count: int = 3,
) -> List[TimeSlot]:
    """Find available time slots within a given range"""
    return ctx.deps.calendar.find_available_slots(start_time, end_time, duration, count)


@calendar_agent.tool
async def check_day_availability(
    ctx: RunContext[CalendarDependencies], date: datetime
) -> bool:
    """Check if a specific day has significant free time"""
    return ctx.deps.calendar.check_day_availability(date)


@calendar_agent.tool
async def schedule_appointment(
    ctx: RunContext[CalendarDependencies],
    title: str,
    start_time: datetime,
    duration: int = 60,
) -> CalendarResponse:
    """Schedule a new appointment"""
    return ctx.deps.calendar.schedule_appointment(title, start_time, duration)


def run_with_calendar(
    prompt: str,
    history: List[Message],
    calendar_service: CalendarService,
    calendar_id: int,
):
    """Run the agent with calendar dependencies properly set up"""
    logfire.info("calendar_agent run", prompt=prompt)
    calendar = CalendarTool(calendar_service)
    calendar.set_active_calendar(calendar_id)
    deps = CalendarDependencies(calendar=calendar, conversation_history=history)
    # Update system prompt with current history
    calendar_agent.system_prompt = get_system_prompt(history)
    response = calendar_agent.run(prompt, deps=deps)
    logfire.info("calendar_agent response", response=response)
    return response


def run_with_calendar_sync(
    prompt: str,
    history: List[Message],
    calendar_service: CalendarService,
    calendar_id: int,
):
    """Synchronous version of run_with_calendar"""
    logfire.info("calendar_agent run_sync", prompt=prompt)
    calendar = CalendarTool(calendar_service)
    calendar.set_active_calendar(calendar_id)
    deps = CalendarDependencies(calendar=calendar, conversation_history=history)
    # Update system prompt with current history
    calendar_agent.system_prompt = get_system_prompt(history)
    response = calendar_agent.run_sync(prompt, deps=deps)
    logfire.info("calendar_agent response", response=response)
    return response
