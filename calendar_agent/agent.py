from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union, Literal

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, models

from .calendar_tool import CalendarTool, TimeSlot
from .config import config


@dataclass
class CalendarDependencies:
    calendar: CalendarTool


class ResponseType(str, Enum):
    BASE = "base"
    CALENDAR = "calendar"


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
    system_prompt="""
    You are a helpful calendar assistant for a real estate agent.
    Your job is to help manage their schedule efficiently.
    Always be professional and concise in your responses.

    For simple interactions like greetings or general questions,
    return a BaseResponse with type="base" and just a message.
    Example: {"type": "base", "message": "Hello! How can I help you today?"}

    Only use CalendarResponse with type="calendar" when you need to:
    1. Suggest specific time slots
    2. Check calendar availability
    3. Perform calendar operations
    Example: {"type": "calendar", "message": "I found these slots...", "suggested_slots": [...]}
    
    When suggesting times, format them clearly and consider the agent's existing commitments.
    """,
)


@calendar_agent.tool
async def check_time_available(
    ctx: RunContext[CalendarDependencies], time: datetime, duration: int = 60
) -> bool:
    """Check if a specific time slot is available"""
    return ctx.deps.calendar.check_availability(time, duration)


@calendar_agent.tool
async def find_slots(
    ctx: RunContext[CalendarDependencies],
    start_time: datetime,
    end_time: datetime,
    duration: int = 60,
    count: int = 3,
) -> List[TimeSlot]:
    """Find available time slots within a given range"""
    return ctx.deps.calendar.find_available_slots(start_time, end_time, duration, count)


@calendar_agent.tool
async def check_day_free(
    ctx: RunContext[CalendarDependencies], date: datetime
) -> tuple[bool, Optional[TimeSlot]]:
    """Check if a specific day has significant free time"""
    return ctx.deps.calendar.check_day_availability(date)


async def run_with_calendar(prompt: str) -> Union[BaseResponse, CalendarResponse]:
    """Run the agent with calendar dependencies properly set up"""
    deps = CalendarDependencies(calendar=CalendarTool())
    return await calendar_agent.run(prompt, deps=deps)


def run_with_calendar_sync(prompt: str) -> Union[BaseResponse, CalendarResponse]:
    """Synchronous version of run_with_calendar"""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(run_with_calendar(prompt))
