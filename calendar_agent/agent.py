import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Literal, Optional, Union, Any

import logfire
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, models

from .calendar_tool import AppointmentStatus, CalendarService, CalendarTool, TimeSlot
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
    conflicts: Optional[List] = Field(
        default=None, description="Conflicting appointments"
    )
    resolved: Optional[List] = Field(default=None, description="Resolved conflicts")
    unresolved: Optional[List] = Field(default=None, description="Unresolved conflicts")


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
        "message": "I found several available time slots tomorrow afternoon:\\n1. 12:00 PM - 1:00 PM\\n2. 1:00 PM - 2:00 PM\\n3. 3:00 PM - 4:00 PM",
        "action_taken": "Found available slots",
        "suggested_slots": [...]
    }}
    
    4. Resolving conflicts:
    {{
        "type": "calendar",
        "message": "I've rescheduled your conflicting appointments to accommodate the high-priority meeting.",
        "action_taken": "Resolved conflicts for appointment 123",
        "resolved": [
            {{
                "id": 456,
                "title": "Team Meeting",
                "action": "rescheduled",
                "start_time": "2025-02-27T10:00:00+00:00"
            }}
        ],
        "unresolved": []
    }}
    
    When resolving conflicts, you can use the resolve_conflicts tool with these parameters:
    - for_appointment_id: The ID of the high-priority appointment
    - use_priority_based: Set to true to prioritize higher priority appointments
    - type_based_strategies: For more complex requests, specify different strategies for different appointment types
      Example for "cancel all internal meetings and reschedule Mrs. Wang's showing to tomorrow afternoon":
      {{
        "internal": {{
            "action": "cancel"
        }},
        "client_meeting": {{
            "action": "reschedule",
            "target_window": "2025-02-27T14:00-17:00"
        }}
      }}
    - reschedule_window_days: How many days to look ahead for rescheduling
    - preferred_hours: Business hours to prefer for rescheduling (e.g., [9, 10, 11, 14, 15, 16])
    
    Example for complex natural language request:
    User: "Please help me cancel all internal meetings and reschedule Mrs. Wang's showing to tomorrow afternoon"
    
    You should:
    1. Find the appointment ID for Mrs. Wang's showing
    2. Use resolve_conflicts with type-based strategies:
       resolve_conflicts(
         for_appointment_id=wang_showing_id,
         use_priority_based=True,
         type_based_strategies={{
           "internal": {{
             "action": "cancel"
           }},
           "client_meeting": {{
             "action": "reschedule",
             "target_window": "2025-02-27T14:00-17:00"
           }}
         }}
       )
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
    priority: int = 3,
    description: str = None,
    location: str = None,
) -> CalendarResponse:
    """
    Schedule a new appointment

    Args:
        title: Title of the appointment
        start_time: Start time of the appointment
        duration: Duration in minutes (default: 60)
        priority: Priority of the appointment (1-5, lower is higher priority)
        description: Optional description
        location: Optional location

    Returns:
        CalendarResponse with scheduling result
    """
    # Calculate end time
    end_time = start_time + timedelta(minutes=duration)

    # Try to schedule the appointment
    success, appointment_dict, conflicts = ctx.deps.calendar.schedule_appointment(
        title=title,
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=priority,
        description=description,
        location=location,
    )

    if success:
        # Format the response with a clear time format
        formatted_date = start_time.strftime("%B %d")
        formatted_time = start_time.strftime("%I:%M %p").lstrip(
            "0"
        )  # Remove leading zero
        formatted_duration = f"{duration} minutes" if duration != 60 else "1 hour"

        # Prepare message about conflicts
        conflicts_msg = ""
        if conflicts and len(conflicts) > 0:
            conflict_titles = [appt["title"] for appt in conflicts]
            conflicts_msg = f" Note: This appointment conflicts with: {', '.join(conflict_titles)}. You may want to resolve these conflicts."

        return CalendarResponse(
            type=ResponseType.CALENDAR,
            message=f"Successfully scheduled '{title}' for {formatted_date} at {formatted_time} for {formatted_duration}.{conflicts_msg}",
            action_taken=f"Scheduled: {title}",
            suggested_slots=None,
            conflicts=conflicts if conflicts else None,
        )
    else:
        return CalendarResponse(
            type=ResponseType.CALENDAR,
            message=f"Sorry, the time slot from {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')} is not available.",
            action_taken="Failed: Time slot not available",
            suggested_slots=None,
        )


@calendar_agent.tool
async def resolve_conflicts(
    ctx: RunContext[CalendarDependencies],
    for_appointment_id: int,
    use_priority_based: bool = True,
    type_based_strategies: Optional[Dict[str, Dict[str, Any]]] = None,
    reschedule_window_days: int = 2,
    preferred_hours: Optional[List[int]] = None,
) -> CalendarResponse:
    """
    Resolve conflicts for a previously scheduled appointment
    
    Args:
        for_appointment_id: ID of the appointment to resolve conflicts for
        use_priority_based: Whether to use priority-based resolution (default: True)
        type_based_strategies: Dictionary of strategies for different appointment types
            Example:
            {
                "internal": {"action": "cancel"},
                "client_meeting": {"action": "reschedule", "target_window": "2025-02-27T14:00-17:00"}
            }
        reschedule_window_days: Number of days to look ahead for rescheduling (default: 2)
        preferred_hours: List of preferred hours (9-17) to try first (default: [9, 10, 11, 14, 15, 16])
    
    Returns:
        CalendarResponse with resolution result
    """
    # Create a simplified strategies structure that's easier for the LLM to work with
    if preferred_hours is None:
        preferred_hours = [9, 10, 11, 14, 15, 16]
    
    # Map the simple parameters to the more complex structure expected by the service
    strategies = {
        "by_priority": use_priority_based,
        "fallback": {
            "action": "reschedule",
            "window_days": reschedule_window_days,
            "preferred_hours": preferred_hours
        }
    }
    
    # Add type-based strategies if provided
    if type_based_strategies:
        strategies["by_type"] = type_based_strategies
    
    # Try to resolve conflicts
    resolved, unresolved = ctx.deps.calendar.resolve_conflicts(
        for_appointment_id=for_appointment_id,
        strategies=strategies,
    )

    # Prepare message about resolved conflicts
    resolved_msg = ""
    if resolved and len(resolved) > 0:
        # Group resolved conflicts by type and action
        by_type_action = {}
        for appt in resolved:
            appt_type = appt.get("type", "other")
            action = appt.get("action", "modified")

            if appt_type not in by_type_action:
                by_type_action[appt_type] = {}

            if action not in by_type_action[appt_type]:
                by_type_action[appt_type][action] = []

            by_type_action[appt_type][action].append(appt)

        # Create a more detailed message
        type_messages = []
        for appt_type, actions in by_type_action.items():
            action_messages = []
            for action, appts in actions.items():
                if action == "rescheduled":
                    # Format the rescheduled appointments with their new times
                    appt_details = [
                        f"{appt['title']} to {datetime.fromisoformat(appt['start_time']).strftime('%B %d at %I:%M %p')}"
                        for appt in appts
                    ]
                else:
                    # Just list the appointment titles for other actions
                    appt_details = [appt["title"] for appt in appts]

                action_messages.append(
                    f"{action.capitalize()} {len(appts)} {appt_type} appointment(s): {', '.join(appt_details)}"
                )

            type_messages.append(". ".join(action_messages))

        resolved_msg = (
            "Successfully resolved conflicts: " + ". ".join(type_messages) + "."
        )

    # Prepare message about unresolved conflicts
    unresolved_msg = ""
    if unresolved and len(unresolved) > 0:
        # Group unresolved conflicts by type
        by_type = {}
        for appt in unresolved:
            appt_type = appt.get("type", "other")

            if appt_type not in by_type:
                by_type[appt_type] = []

            by_type[appt_type].append(appt)

        # Create a more detailed message
        type_messages = []
        for appt_type, appts in by_type.items():
            appt_titles = [appt["title"] for appt in appts]
            type_messages.append(
                f"{len(appts)} {appt_type} appointment(s): {', '.join(appt_titles)}"
            )

        unresolved_msg = " Could not resolve: " + ", ".join(type_messages) + "."

    # If nothing was resolved or unresolved, provide a generic message
    if not resolved_msg and not unresolved_msg:
        message = f"No conflicts found for appointment {for_appointment_id}."
    else:
        message = f"{resolved_msg}{unresolved_msg}"

    return CalendarResponse(
        type=ResponseType.CALENDAR,
        message=message,
        action_taken=f"Resolved conflicts for appointment {for_appointment_id}",
        suggested_slots=None,
        resolved=resolved if resolved else None,
        unresolved=unresolved if unresolved else None,
    )


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
    # Ensure logs are sent to Logfire
    logfire.force_flush()
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
    # Ensure logs are sent to Logfire
    logfire.force_flush()
    return response
