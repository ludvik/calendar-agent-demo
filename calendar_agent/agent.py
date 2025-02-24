from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, models

from .calendar_tool import CalendarTool, TimeSlot
from .config import config


@dataclass
class CalendarDependencies:
    calendar: CalendarTool


class CalendarResponse(BaseModel):
    message: str = Field(description="Natural language response to the user")
    suggested_slots: Optional[List[TimeSlot]] = Field(
        default=None,
        description="List of suggested time slots if applicable"
    )
    action_taken: Optional[str] = Field(
        default=None,
        description="Description of any actions taken"
    )


# Configure LLM based on settings
if config.is_using_real_llm:
    models.ALLOW_MODEL_REQUESTS = True
    logger.info("Using OpenAI GPT-4 model")
else:
    logger.warning("No OpenAI API key found. Using test model (mock responses)")


calendar_agent = Agent(
    'openai:gpt-4',  # You can change this to your preferred model
    deps_type=CalendarDependencies,
    result_type=CalendarResponse,
    system_prompt="""
    You are a helpful calendar assistant for a real estate agent.
    Your job is to help manage their schedule efficiently.
    Always be professional and concise in your responses.
    When suggesting times, format them clearly and consider the agent's existing commitments.
    """
)


@calendar_agent.tool
async def check_time_available(
    ctx: RunContext[CalendarDependencies],
    time: datetime,
    duration: int = 60
) -> bool:
    """Check if a specific time slot is available"""
    return ctx.deps.calendar.check_availability(time, duration)


@calendar_agent.tool
async def find_slots(
    ctx: RunContext[CalendarDependencies],
    start_time: datetime,
    end_time: datetime,
    duration: int = 60,
    count: int = 3
) -> List[TimeSlot]:
    """Find available time slots within a given range"""
    return ctx.deps.calendar.find_available_slots(
        start_time,
        end_time,
        duration,
        count
    )


@calendar_agent.tool
async def check_day_free(
    ctx: RunContext[CalendarDependencies],
    date: datetime
) -> tuple[bool, Optional[TimeSlot]]:
    """Check if a specific day has significant free time"""
    return ctx.deps.calendar.check_day_availability(date)
