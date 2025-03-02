import sys
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

"""
Calendar agent implementation.

Note on timezone handling:
- The calendar service internally works with UTC timezone
- This agent layer is responsible for converting between UTC and local timezone for display
- In this demo version, only the find_available_time_slots function has been updated with proper timezone conversion
- Other functions may still display times in UTC
- For production use, all time-related functions should be updated with proper timezone handling
"""

import logfire
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, models

from .calendar_service import CalendarService
from .config import config
from .models import Appointment, AppointmentStatus
from .response import BaseResponse, CalendarResponse, ResponseType, TimeSlot


class Message(BaseModel):
    """Message in conversation history"""

    role: str
    content: str


class AppointmentReference(BaseModel):
    """Reference to an appointment in conversation context"""

    id: int
    title: str
    start_time: datetime
    end_time: datetime
    priority: int
    mentioned_at: datetime = Field(default_factory=datetime.now)

    @property
    def is_recent(self) -> bool:
        """Check if this reference was mentioned recently (within last 5 messages)"""
        return (datetime.now() - self.mentioned_at).total_seconds() < 300  # 5 minutes


class CalendarDependencies(BaseModel):
    """Dependencies for calendar agent"""

    calendar_service: CalendarService
    conversation_history: List[Message]

    model_config = {"arbitrary_types_allowed": True}


# Define response types using Literal
ResponseType = Literal["BASE", "CALENDAR"]


class BaseResponse(BaseModel):
    """Base response for simple interactions that don't require calendar operations"""

    type: ResponseType = "BASE"
    message: str = Field(description="Natural language response to the user")


class CalendarResponse(BaseModel):
    """Response type for calendar-specific operations"""

    type: ResponseType = "CALENDAR"
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
    """Extract context from conversation history"""
    if not history:
        return "No previous conversation."

    # Take the last few messages for context
    recent_messages = history[-10:]  # Last 10 messages

    context_parts = []
    for msg in recent_messages:
        role = msg.role.capitalize()
        # Truncate long messages to 500 characters
        content = msg.content[:500]
        if len(msg.content) > 500:
            content += "..."
        context_parts.append(f"{role}: {content}")

    return "\n".join(context_parts)


def get_system_prompt(history: List[Message]) -> str:
    """Get system prompt with current time and conversation history"""
    # Get current time
    current_time = datetime.now(timezone.utc)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

    # Extract context from conversation history
    context = get_conversation_context(history)

    # Render system prompt with current time and context
    rendered_system_prompt = f"""
    You are a helpful calendar assistant for a real estate agent.
    Current time: {formatted_time}
    
    {context}
    
    SCHEDULING PRINCIPLES:
    1. Prioritize appointments based on their priority (1-5, where 1 is highest)
    2. Avoid scheduling conflicts whenever possible
    3. Provide a clear title, start time, and duration
    4. Handle the scheduling result appropriately:
       * If successful with no conflicts: Inform the user of the successful scheduling
       * If successful with conflicts: Inform the user of the successful scheduling and mention the conflicts
       * If unsuccessful: Explain why and suggest alternatives

    DATETIME HANDLING:
    - All datetime values must be in UTC timezone
    - When receiving datetime strings, convert them to datetime objects using datetime.fromisoformat()
    - Always replace 'Z' in ISO format strings with '+00:00' for proper timezone parsing
    - Use the ensure_utc() function to guarantee timezone awareness
    - SQLite has limitations with timezone storage - all retrieved datetimes should be treated as UTC

    CONTEXT MANAGEMENT:
    - Use appointment IDs when modifying or resolving conflicts
    - NEVER create new appointments when user refers to existing ones
    - For operations on existing appointments, use the appropriate method with the appointment's ID:
      * Rescheduling: batch_update (for single or multiple appointments)
      * Cancellation: cancel_appointment
    
    RESPONSE FORMATTING:
    - For calendar operations: Use CalendarResponse with type="CALENDAR" including:
      * Natural language message describing the action
      * Specific action taken
      * Relevant appointment details (title, date, time, duration)
      * For availability checks: whether time is available or what's blocking it
      * For time slot suggestions: list of available slots in clear format

    AVAILABLE TOOLS:
    1. schedule_appointment - Create a new appointment with title, start_time, duration, priority, etc.
    2. check_availability - Check if a specific time slot is available
    3. find_available_time_slots - Find multiple available time slots within a date range
    4. check_day_availability - Check if a specific day has significant free time
    5. get_appointments - Retrieve appointments within a time range with optional filtering
    6. cancel_appointment - Cancel an existing appointment by ID
    7. batch_update - Update multiple appointments in a single operation
    8. get_appointment - Get details of a specific appointment by ID

    SUGGESTING AVAILABLE TIME SLOTS:
    - Use find_available_time_slots to suggest available time slots within a given range
    - TIMESLOTS always start at 30 minute intervals (00, 30)

    SUGGESTIONS FOR VARIOUS TIME SLOT RELATED QUERIES:
    - Use find_available_time_slots to find available time slots within a given range
    - Use check_availability to check if a specific time is available
    - Use check_day_availability to check if a specific day has significant free time
    
    BATCH OPERATIONS:
    - ALWAYS use batch_update when handling appointment changes, including:
      * Updating a single appointment
      * Rescheduling one appointment requires changing others
      * When cancelling multiple appointments of the same type
      * When applying the same change to multiple appointments
    
    - batch_update accepts a list of update operations, each containing:
      * appointment_id: ID of the appointment to update (required)
      * start_time: New start time (optional) - must be a datetime object or ISO format string
      * end_time: New end time (optional) - must be a datetime object or ISO format string
      * status: New status (CONFIRMED, TENTATIVE, CANCELLED) (optional)
      * priority: New priority (1-5, where 1 is highest) (optional)
      * title: New title (optional)
      * description: New description (optional)
      * location: New location (optional)
    
    - Example usage:
      batch_update([
        {{"appointment_id": 1, "start_time": "2025-03-01T10:00:00Z", "end_time": "2025-03-01T11:00:00Z"}},
        {{"appointment_id": 2, "status": "CANCELLED"}},
        {{"appointment_id": 3, "priority": 1, "location": "Main Office"}}
      ])
    
    - AVOID these common mistakes:
      * Checking availability before scheduling (redundant)
      * Not providing specific appointment IDs when updating or cancelling
      * Suggesting complex rescheduling without checking availability
      * Forgetting to provide detailed appointment information when querying
      * Using naive datetime objects without timezone information
      * Not handling string-to-datetime conversion properly

    Remember to verify operations, check for conflicts after each action, and maintain conversation continuity.
    """

    logger.debug(
        f"get_system_prompt -> rendered_system_prompt: {rendered_system_prompt}"
    )

    return rendered_system_prompt


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
    ctx: RunContext[CalendarDependencies],
    calendar_id: int = None,
    time: datetime = None,
    duration: int = 60,
) -> CalendarResponse:
    """Check if a specific time is available.

    Args:
        time: Time to check
        duration: Duration in minutes (default: 60)
        ctx: Agent context
        calendar_id: Calendar ID (optional)

    Returns:
        CalendarResponse: Response with availability info
    """
    if not ctx:
        raise ValueError("Context required")

    # Calculate end time
    end_time = time + timedelta(minutes=duration)

    # Check availability directly using the calendar service
    is_available = ctx.deps.calendar_service.check_availability(
        calendar_id=calendar_id, start_time=time, end_time=end_time
    )

    # Format response
    formatted_time = time.strftime("%I:%M %p").lstrip("0")  # Remove leading zero
    formatted_duration = f"{duration} minutes" if duration != 60 else "1 hour"

    if is_available:
        return CalendarResponse(
            type="CALENDAR",
            message=f"The time slot at {formatted_time} for {formatted_duration} is available.",
            action_taken=f"Checked availability for {formatted_time}",
            suggested_slots=None,
        )
    else:
        return CalendarResponse(
            type="CALENDAR",
            message=f"Sorry, the time slot at {formatted_time} for {formatted_duration} is not available.",
            action_taken=f"Checked availability for {formatted_time}",
            suggested_slots=None,
        )


@calendar_agent.tool
async def find_available_time_slots(
    ctx: RunContext[CalendarDependencies],
    calendar_id: int = None,
    start_time: datetime = None,
    end_time: datetime = None,
    duration: int = 60,
    count: int = 3,
) -> CalendarResponse:
    """Find available time slots within a given range"""
    if not ctx or not ctx.deps or not ctx.deps.calendar_service:
        return CalendarResponse(
            message="Calendar service not available",
        )

    # Get current date for default values
    now = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()  # Local time with timezone info
    local_tz = local_now.tzinfo

    # Default calendar_id if not provided
    if calendar_id is None:
        # Try to get the first calendar from the service
        try:
            calendar_id = 1  # Default to ID 1 if no specific ID provided
        except Exception:
            return CalendarResponse(
                message="No calendar ID provided and couldn't determine default",
            )

    # Default time range (9am-5pm today) in local time, converted to UTC for processing
    if start_time is None:
        # Set default business hours (9am-5pm in local time)
        local_start = local_now.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # If current local time is after 9am, use current time as start
        if local_now.hour >= 9:
            local_start = local_now
            
        # Convert to UTC for internal processing
        start_time = local_start.astimezone(timezone.utc)

    if end_time is None:
        local_end = local_now.replace(hour=17, minute=0, second=0, microsecond=0)
        
        # If current local time is after 5pm, use tomorrow
        if local_now.hour >= 17:
            local_start = (local_now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            local_end = (local_now + timedelta(days=1)).replace(
                hour=17, minute=0, second=0, microsecond=0
            )
            
            # Update start_time as well for the next day
            start_time = local_start.astimezone(timezone.utc)
            
        # Convert to UTC for internal processing
        end_time = local_end.astimezone(timezone.utc)

    try:
        # Use calendar_service directly
        calendar_service = ctx.deps.calendar_service

        # Find available slots using the service method
        available_time_slots = calendar_service.find_available_slots(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            max_slots=count,
            priority=5,  # Default priority
        )
        
        # Convert to TimeSlot objects with formatted times
        available_slots = []
        for slot_start, slot_end in available_time_slots:
            # Convert UTC times to local timezone for display
            local_tz = datetime.now().astimezone().tzinfo
            
            # Ensure times are in UTC before converting to local
            if slot_start.tzinfo != timezone.utc:
                slot_start = slot_start.replace(tzinfo=timezone.utc)
            if slot_end.tzinfo != timezone.utc:
                slot_end = slot_end.replace(tzinfo=timezone.utc)
                
            # Convert to local timezone
            local_start = slot_start.astimezone(local_tz)
            local_end = slot_end.astimezone(local_tz)
                
            # Format times as strings without seconds
            start_str = local_start.strftime("%Y-%m-%d %H:%M")
            end_str = local_end.strftime("%Y-%m-%d %H:%M")
            
            available_slots.append(
                TimeSlot(
                    start_time=start_str,
                    end_time=end_str,
                    duration=duration,
                )
            )

        # Add a note about time zone in the message
        local_tz_name = datetime.now().astimezone().tzname()
        message = f"Found {len(available_slots)} available time slots (all times in {local_tz_name})"
        
        return CalendarResponse(
            message=message,
            suggested_slots=available_slots,
        )
    except Exception as e:
        logger.error(f"Error finding available time slots: {e}")
        return CalendarResponse(
            message=f"Error finding available time slots: {e}",
            error=str(e),
        )


@calendar_agent.tool
async def check_day_availability(
    ctx: RunContext[CalendarDependencies], calendar_id: int, date: datetime
) -> CalendarResponse:
    """Check if a specific day has significant free time"""
    if not ctx or not ctx.deps or not ctx.deps.calendar_service:
        return CalendarResponse(
            message="Calendar service not available",
        )

    try:
        # Use calendar_service directly
        calendar_service = ctx.deps.calendar_service

        # Business hours
        business_start = time(9, 0)
        business_end = time(17, 0)

        # Get all appointments for the day
        start_time = datetime.combine(date.date(), business_start)
        end_time = datetime.combine(date.date(), business_end)
        success, appointments = calendar_service.get_appointments_in_range(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
        )

        if not success:
            return CalendarResponse(
                message="Failed to retrieve appointments.",
                action_taken="Failed: Could not get appointments",
            )

        # Build list of busy slots
        busy_slots = []
        for appt in appointments:
            busy_slots.append(
                {"start": appt.start_time, "end": appt.end_time, "title": appt.title}
            )

        # Format message
        if not busy_slots:
            message = (
                f"The entire day from {business_start} to {business_end} is available."
            )
            action_taken = "Found: Day is completely free"
        else:
            busy_times = [
                f"{slot['start'].strftime('%I:%M %p')} - {slot['end'].strftime('%I:%M %p')}: {slot['title']}"
                for slot in busy_slots
            ]
            message = f"Busy times:\n" + "\n".join(busy_times)
            action_taken = f"Found {len(busy_slots)} appointments"

        return CalendarResponse(
            message=message,
            action_taken=action_taken,
        )
    except Exception as e:
        return CalendarResponse(
            message=f"Error checking day availability: {str(e)}",
        )


@calendar_agent.tool
async def schedule_appointment(
    ctx: RunContext[CalendarDependencies],
    calendar_id: int,
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
        calendar_id: Calendar ID
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

    # Try to schedule the appointment directly using the calendar service
    success, appointment, conflicts = ctx.deps.calendar_service.schedule_appointment(
        calendar_id=calendar_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=priority,
        description=description,
        location=location,
    )

    # Convert conflicts to dict format
    conflicts_dict = []
    for appt in conflicts:
        conflicts_dict.append(
            {
                "id": appt.id,
                "title": appt.title,
                "start_time": appt.start_time.isoformat(),
                "end_time": appt.end_time.isoformat(),
                "status": appt.status.value,
                "priority": appt.priority,
                "description": appt.description,
                "location": appt.location,
                "type": ctx.deps.calendar_service.get_appointment_type(appt),
            }
        )

    if success:
        # Format the response with a clear time format
        formatted_date = start_time.strftime("%B %d")
        formatted_time = start_time.strftime("%I:%M %p").lstrip(
            "0"
        )  # Remove leading zero
        formatted_duration = f"{duration} minutes" if duration != 60 else "1 hour"

        # Convert appointment to dict for the response
        appointment_dict = {
            "id": appointment.id,
            "title": appointment.title,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "status": appointment.status.value,
            "priority": appointment.priority,
            "description": appointment.description,
            "location": appointment.location,
            "type": ctx.deps.calendar_service.get_appointment_type(appointment),
        }

        # Prepare message about conflicts
        conflicts_msg = ""
        if conflicts_dict:
            conflict_details = []
            for appt in conflicts_dict:
                conflict_details.append(
                    f"{appt['title']} at {appt['start_time']} (ID: {appt['id']})"
                )
            conflicts_msg = (
                f" However, it conflicts with the following appointments:\n- "
                + "\n- ".join(conflict_details)
            )
            conflicts_msg += "\nYou may want to resolve these conflicts."

        return CalendarResponse(
            type="CALENDAR",
            message=f"Successfully scheduled '{title}' for {formatted_date} at {formatted_time} for {formatted_duration}.{conflicts_msg}",
            action_taken=f"Scheduled: '{title}'",
            conflicts=conflicts_dict if conflicts_dict else None,
        )
    else:
        # Format conflict details for the error message
        conflict_details = []
        for appt in conflicts_dict:
            conflict_details.append(
                f"{appt['title']} at {datetime.fromisoformat(appt['start_time']).strftime('%I:%M %p')} (Priority: {appt['priority']})"
            )

        conflicts_msg = ""
        if conflict_details:
            conflicts_msg = "\nConflicts with:\n- " + "\n- ".join(conflict_details)

        return CalendarResponse(
            type="CALENDAR",
            message=f"Sorry, the time slot from {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')} is not available.{conflicts_msg}",
            action_taken="Failed: Time slot not available",
            conflicts=conflicts_dict if conflicts_dict else None,
        )


@calendar_agent.tool
async def get_appointment(
    ctx: RunContext[CalendarDependencies], calendar_id: int, appointment_id: int
) -> Dict:
    """Get details of a specific appointment by ID"""
    return ctx.deps.calendar.get_appointment(calendar_id, appointment_id)


@calendar_agent.tool
async def get_appointments(
    ctx: RunContext[CalendarDependencies],
    calendar_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    title_filter: Optional[str] = None,
    priority: Optional[int] = None,
) -> CalendarResponse:
    """Get appointments within a time range with optional filters"""
    try:
        # Get the calendar service from dependencies
        calendar_service = ctx.deps.calendar_service

        # Set default time range if not provided
        if not start_time:
            start_time = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if not end_time:
            end_time = datetime.now(timezone.utc) + timedelta(days=7)

        # Get appointments in range
        success, appointments = calendar_service.get_appointments_in_range(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
        )

        if not success or not appointments:
            time_range_msg = ""
            if start_time and end_time:
                time_range_msg = f" between {start_time.strftime('%Y-%m-%d')} and {end_time.strftime('%Y-%m-%d')}"

            return CalendarResponse(
                type="CALENDAR",
                message=f"No appointments found{time_range_msg}.",
                action_taken="No appointments found",
            )

        # Apply filters
        filtered_appointments = []
        for appointment in appointments:
            # Skip cancelled appointments
            if appointment.status == AppointmentStatus.CANCELLED:
                continue

            # Apply title filter if specified
            if title_filter and title_filter.lower() not in appointment.title.lower():
                continue

            # Apply priority filter if specified
            if priority is not None and appointment.priority != priority:
                continue

            filtered_appointments.append(appointment)

        # Format appointment details for better readability
        formatted_appointments = []
        for appt in filtered_appointments:
            start_time_str = appt.start_time.strftime("%I:%M %p").lstrip("0")
            end_time_str = appt.end_time.strftime("%I:%M %p").lstrip("0")
            formatted_date = appt.start_time.strftime("%B %d")

            formatted_appointments.append(
                f"{appt.title} on {formatted_date} from {start_time_str} to {end_time_str} (Priority: {appt.priority}, ID: {appt.id})"
            )

        if title_filter:
            if filtered_appointments:
                details = "\n- " + "\n- ".join(formatted_appointments)
                return CalendarResponse(
                    type="CALENDAR",
                    message=f"Found {len(filtered_appointments)} appointments matching '{title_filter}':{details}",
                    action_taken=f"Found {len(filtered_appointments)} appointments",
                )
            else:
                return CalendarResponse(
                    type="CALENDAR",
                    message=f"No appointments found with title containing '{title_filter}'.",
                    action_taken="No appointments found",
                )
        elif filtered_appointments:
            details = "\n- " + "\n- ".join(formatted_appointments)
            time_range_msg = ""
            if start_time and end_time:
                start_date = start_time.strftime("%Y-%m-%d")
                end_date = end_time.strftime("%Y-%m-%d")
                if start_date == end_date:
                    time_range_msg = f" for {start_date}"
                else:
                    time_range_msg = f" between {start_date} and {end_date}"

            return CalendarResponse(
                type="CALENDAR",
                message=f"Found {len(filtered_appointments)} appointments{time_range_msg}:{details}",
                action_taken=f"Found {len(filtered_appointments)} appointments",
            )
        else:
            time_range_msg = ""
            if start_time and end_time:
                time_range_msg = f" between {start_time.strftime('%Y-%m-%d')} and {end_time.strftime('%Y-%m-%d')}"

            return CalendarResponse(
                type="CALENDAR",
                message=f"No appointments found{time_range_msg}.",
                action_taken="No appointments found",
            )
    except Exception as e:
        logger.error(f"Error in get_appointments: {e}")
        return CalendarResponse(
            type="CALENDAR",
            message=f"Error retrieving appointments: {str(e)}",
            action_taken="Failed: Could not retrieve appointments",
        )


@calendar_agent.tool
async def cancel_appointment(
    ctx: RunContext[CalendarDependencies], calendar_id: int, appointment_id: int
) -> CalendarResponse:
    """Cancel an appointment by ID"""
    try:
        # Get the calendar service from dependencies
        calendar_service = ctx.deps.calendar_service

        # Get the appointment before cancelling to include in the response
        with calendar_service.session_factory() as session:
            appointment = (
                session.query(Appointment)
                .filter_by(id=appointment_id, calendar_id=calendar_id)
                .first()
            )

            if not appointment:
                return CalendarResponse(
                    type="CALENDAR",
                    message=f"Failed to cancel appointment {appointment_id}: Appointment not found.",
                    action_taken="Failed: Appointment not found",
                )

            # Store appointment details before cancelling
            appointment_title = appointment.title
            appointment_start = appointment.start_time

            # Cancel the appointment
            appointment.status = AppointmentStatus.CANCELLED
            appointment.updated_at = datetime.now(timezone.utc)
            session.commit()

            # Format the response
            formatted_date = appointment_start.strftime("%B %d")
            formatted_time = appointment_start.strftime("%I:%M %p").lstrip("0")

            return CalendarResponse(
                type="CALENDAR",
                message=f"Successfully cancelled appointment '{appointment_title}' scheduled for {formatted_date} at {formatted_time}.",
                action_taken=f"Cancelled: {appointment_title}",
            )
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}")
        return CalendarResponse(
            type="CALENDAR",
            message=f"Failed to cancel appointment {appointment_id}: {str(e)}",
            action_taken="Failed: Could not cancel appointment",
        )


@calendar_agent.tool
async def batch_update(
    ctx: RunContext[CalendarDependencies], updates: List[Dict[str, Any]]
) -> CalendarResponse:
    """
    Batch update multiple appointments with different changes.

    Args:
        ctx: Run context
        updates: List of update operations, each containing:
            - appointment_id: ID of the appointment to update
            - start_time: (Optional) New start time
            - end_time: (Optional) New end_time
            - status: (Optional) New status (CONFIRMED, TENTATIVE, CANCELLED)
            - priority: (Optional) New priority (1-5, where 1 is highest)
            - title: (Optional) New title
            - description: (Optional) New description
            - location: (Optional) New location

    Returns:
        CalendarResponse with results of the batch update
    """
    if not updates:
        return CalendarResponse(
            type="CALENDAR",
            message="No updates provided.",
            action_taken="No action taken",
        )

    # Get the calendar service from dependencies
    calendar_service = ctx.deps.calendar_service

    successful_updates = []
    failed_updates = []
    all_conflicts = []

    for update in updates:
        appointment_id = update.get("appointment_id")
        if not appointment_id:
            failed_updates.append({"error": "Missing appointment_id", "update": update})
            continue

        # Extract optional parameters
        calendar_id = update.get("calendar_id")
        start_time = update.get("start_time")
        end_time = update.get("end_time")
        status_str = update.get("status")
        priority = update.get("priority")
        title = update.get("title")
        description = update.get("description")
        location = update.get("location")

        # Convert string dates to datetime objects if needed
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                failed_updates.append(
                    {
                        "error": f"Invalid start_time format: {start_time}",
                        "appointment_id": appointment_id,
                    }
                )
                continue

        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                failed_updates.append(
                    {
                        "error": f"Invalid end_time format: {end_time}",
                        "appointment_id": appointment_id,
                    }
                )
                continue

        # Convert status string to enum if provided
        status = None
        if status_str:
            try:
                status = AppointmentStatus(status_str)
            except ValueError:
                failed_updates.append(
                    {
                        "error": f"Invalid status: {status_str}",
                        "appointment_id": appointment_id,
                    }
                )
                continue

        # Perform the update directly using calendar_service
        try:
            success, updated_appointment, conflicts = (
                calendar_service.update_appointment(
                    calendar_id=calendar_id,
                    appointment_id=appointment_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    status=status,
                    priority=priority,
                    description=description,
                    location=location,
                )
            )

            if success and updated_appointment:
                successful_updates.append(
                    {
                        "appointment_id": appointment_id,
                        "title": updated_appointment.title,
                        "changes": {
                            k: v for k, v in update.items() if k != "appointment_id"
                        },
                    }
                )

                if conflicts:
                    for conflict in conflicts:
                        all_conflicts.append(
                            {
                                "appointment_id": conflict.id,
                                "title": conflict.title,
                                "start_time": conflict.start_time,
                                "end_time": conflict.end_time,
                                "priority": conflict.priority,
                                "conflicts_with": appointment_id,
                            }
                        )
            else:
                failed_updates.append(
                    {"error": "Update failed", "appointment_id": appointment_id}
                )
        except Exception as e:
            failed_updates.append({"error": str(e), "appointment_id": appointment_id})

    # Prepare response message
    if successful_updates and not failed_updates:
        message = f"Successfully updated {len(successful_updates)} appointments."
        if all_conflicts:
            message += (
                f" Found {len(all_conflicts)} conflicts that may need resolution."
            )
    elif successful_updates and failed_updates:
        message = f"Partially successful: Updated {len(successful_updates)} appointments, but {len(failed_updates)} updates failed."
        if all_conflicts:
            message += (
                f" Found {len(all_conflicts)} conflicts that may need resolution."
            )
    else:
        message = (
            f"Failed to update any appointments. {len(failed_updates)} updates failed."
        )

    action_taken = f"Batch updated {len(successful_updates)} appointments"

    return CalendarResponse(
        type="CALENDAR",
        message=message,
        action_taken=action_taken,
        conflicts=all_conflicts if all_conflicts else None,
    )


@calendar_agent.tool
async def check_date_range_availability(
    ctx: RunContext[CalendarDependencies], 
    calendar_id: int, 
    start_date: datetime,
    end_date: datetime,
    weekdays_only: bool = False
) -> CalendarResponse:
    """
    Check availability across a date range (e.g., a week) and identify the least busy days.
    
    Args:
        ctx: Run context
        calendar_id: Calendar ID
        start_date: Start date of the range
        end_date: End date of the range
        weekdays_only: If True, only consider weekdays (Monday-Friday)
        
    Returns:
        CalendarResponse with availability information for the date range
    """
    if not ctx or not ctx.deps or not ctx.deps.calendar_service:
        return CalendarResponse(
            message="Calendar service not available",
        )
        
    try:
        # Use calendar_service directly
        calendar_service = ctx.deps.calendar_service
        
        # Business hours
        business_start = time(9, 0)
        business_end = time(17, 0)
        
        # Calculate number of days in the range
        days_delta = (end_date.date() - start_date.date()).days + 1
        
        # Store availability data for each day
        day_availability = []
        
        # Check each day in the range
        current_date = start_date
        for _ in range(days_delta):
            # Skip weekends if weekdays_only is True
            if weekdays_only and current_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                current_date += timedelta(days=1)
                continue
                
            # Get all appointments for the day
            day_start = datetime.combine(current_date.date(), business_start)
            day_end = datetime.combine(current_date.date(), business_end)
            
            success, appointments = calendar_service.get_appointments_in_range(
                calendar_id=calendar_id,
                start_time=day_start,
                end_time=day_end,
            )
            
            if not success:
                return CalendarResponse(
                    message=f"Failed to retrieve appointments for {current_date.date()}.",
                    action_taken="Failed: Could not get appointments",
                )
            
            # Calculate total busy time for the day
            total_busy_minutes = 0
            busy_slots = []
            
            for appt in appointments:
                # Calculate appointment duration in minutes
                duration_minutes = (appt.end_time - appt.start_time).total_seconds() / 60
                total_busy_minutes += duration_minutes
                
                busy_slots.append({
                    "start": appt.start_time,
                    "end": appt.end_time,
                    "title": appt.title,
                    "duration_minutes": duration_minutes
                })
            
            # Calculate free time in hours
            business_day_minutes = (business_end.hour - business_start.hour) * 60
            free_hours = (business_day_minutes - total_busy_minutes) / 60
            
            # Add day data to the list
            day_availability.append({
                "date": current_date.date(),
                "day_of_week": current_date.strftime("%A"),
                "free_hours": round(free_hours, 1),
                "appointment_count": len(appointments),
                "busy_slots": busy_slots
            })
            
            # Move to next day
            current_date += timedelta(days=1)
        
        # Find the least busy day
        if day_availability:
            least_busy_day = max(day_availability, key=lambda x: x["free_hours"])
            
            # Format the response message
            day_summaries = []
            for day_data in day_availability:
                date_str = day_data["date"].strftime("%Y-%m-%d")
                day_name = day_data["day_of_week"]
                free_hours = day_data["free_hours"]
                appt_count = day_data["appointment_count"]
                
                day_summaries.append(
                    f"{day_name} ({date_str}): {free_hours} free hours, {appt_count} appointments"
                )
            
            # Create a more descriptive message
            if weekdays_only:
                range_description = "weekdays"
            else:
                range_description = "days"
                
            message = f"Availability across the {range_description} from {start_date.date()} to {end_date.date()}:\n\n"
            message += "\n".join(day_summaries)
            message += f"\n\nLeast busy day: {least_busy_day['day_of_week']} ({least_busy_day['date']}) with {least_busy_day['free_hours']} free hours"
            
            return CalendarResponse(
                message=message,
                action_taken=f"Analyzed availability for {len(day_availability)} {range_description}",
            )
        else:
            return CalendarResponse(
                message="No days found in the specified range.",
                action_taken="Failed: Invalid date range or no weekdays in range",
            )
            
    except Exception as e:
        return CalendarResponse(
            message=f"Error checking date range availability: {str(e)}",
        )


async def run(
    user_prompt: str,
    calendar_service: CalendarService,
    history: Optional[List[Message]] = None,
):
    """Run the agent with calendar dependencies properly set up"""
    logfire.info("calendar_agent run", prompt=user_prompt)

    deps = CalendarDependencies(
        calendar_service=calendar_service,
        conversation_history=history or [],
    )

    response = await calendar_agent.run(
        user_prompt=user_prompt,
        deps=deps,
    )

    return response


def run_sync(
    user_prompt: str,
    calendar_service: CalendarService,
    history: Optional[List[Message]] = None,
):
    """Run the agent synchronously with calendar dependencies properly set up"""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    deps = CalendarDependencies(
        calendar_service=calendar_service,
        conversation_history=history or [],
    )

    response = loop.run_until_complete(
        calendar_agent.run(
            user_prompt=user_prompt,
            deps=deps,
        )
    )

    return response
