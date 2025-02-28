import asyncio
from datetime import datetime, timedelta

from loguru import logger

from .agent import (
    CalendarDependencies,
    CalendarResponse,
    Message,
    ResponseType,
    calendar_agent,
    get_conversation_context,
    get_system_prompt,
    run_with_calendar,
)
from .calendar_service import CalendarService
from .calendar_tool import AppointmentStatus, CalendarTool
from .config import DatabaseConfig
from .models import Appointment, Calendar


async def setup_test_data(calendar_service, calendar_id):
    """Set up test data with conflicts for manual testing"""
    # Get current date
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Create a series of appointments for today and tomorrow
    test_appointments = [
        # High priority client meeting
        {
            "title": "Client Meeting - Smith Property",
            "start_time": today.replace(hour=10, minute=0),
            "end_time": today.replace(hour=11, minute=0),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 1,  # High priority
            "type": "client_meeting",
            "description": "Discuss listing options for the Smith property",
            "location": "123 Main St",
        },
        # Medium priority internal meeting
        {
            "title": "Team Standup",
            "start_time": today.replace(hour=9, minute=0),
            "end_time": today.replace(hour=9, minute=30),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,  # Medium priority
            "type": "internal",
            "description": "Daily team standup meeting",
            "location": "Office Conference Room",
        },
        # Low priority personal appointment
        {
            "title": "Lunch Break",
            "start_time": today.replace(hour=12, minute=0),
            "end_time": today.replace(hour=13, minute=0),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 4,  # Low priority
            "type": "personal",
            "description": "Lunch break",
            "location": "Office",
        },
        # Tomorrow's appointments
        {
            "title": "Property Viewing - Johnson Family",
            "start_time": today.replace(hour=14, minute=0) + timedelta(days=1),
            "end_time": today.replace(hour=15, minute=30) + timedelta(days=1),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 2,  # High-medium priority
            "type": "client_meeting",
            "description": "Show the Johnson family the new listings",
            "location": "456 Oak Ave",
        },
        {
            "title": "Marketing Strategy Meeting",
            "start_time": today.replace(hour=10, minute=0) + timedelta(days=1),
            "end_time": today.replace(hour=11, minute=30) + timedelta(days=1),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,  # Medium priority
            "type": "internal",
            "description": "Discuss Q2 marketing strategy",
            "location": "Office Conference Room",
        },
    ]

    # Add the appointments to the calendar
    for appt in test_appointments:
        success, appointment, conflicts = calendar_service.schedule_appointment(
            calendar_id=calendar_id,
            title=appt["title"],
            start_time=appt["start_time"],
            end_time=appt["end_time"],
            status=appt["status"],
            priority=appt["priority"],
            description=appt.get("description", ""),
            location=appt.get("location", ""),
        )

        # Add type information to the appointment if successful
        if success and appointment:
            session = calendar_service.session_factory()
            try:
                db_appointment = session.get(Appointment, appointment.id)
                if db_appointment:
                    db_appointment.type = appt.get("type", "other")
                    session.commit()
            except Exception as e:
                logger.error(f"Error setting appointment type: {e}")
            finally:
                session.close()

    # Return a summary of the test data
    return test_appointments


async def main():
    # Initialize database and services
    db_config = DatabaseConfig()
    db_config.init_db()
    calendar_service = CalendarService(db_config.session_factory)

    # Create a default calendar if none exists
    session = db_config.session_factory()
    try:
        default_calendar = session.query(Calendar).first()
        if not default_calendar:
            default_calendar = Calendar(
                agent_id="default_agent", name="Default Calendar", time_zone="UTC"
            )
            session.add(default_calendar)
            session.commit()
            logger.info(f"Created default calendar with id {default_calendar.id}")
        calendar_id = default_calendar.id
    finally:
        session.close()

    # Set up test data
    test_appointments = await setup_test_data(calendar_service, calendar_id)

    # Print test data information
    print("\n===== TEST DATA SETUP =====")
    print("The following appointments have been created for testing:")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_appts = [
        a for a in test_appointments if a["start_time"].date() == today.date()
    ]
    tomorrow_appts = [
        a
        for a in test_appointments
        if a["start_time"].date() == (today + timedelta(days=1)).date()
    ]

    print(f"\nToday's Appointments ({today.strftime('%Y-%m-%d')}):")
    for i, appt in enumerate(today_appts, 1):
        print(
            f"{i}. {appt['title']} - {appt['start_time'].strftime('%I:%M %p')} to {appt['end_time'].strftime('%I:%M %p')} (Priority: {appt['priority']})"
        )

    print(
        f"\nTomorrow's Appointments ({(today + timedelta(days=1)).strftime('%Y-%m-%d')}):"
    )
    for i, appt in enumerate(tomorrow_appts, 1):
        print(
            f"{i}. {appt['title']} - {appt['start_time'].strftime('%I:%M %p')} to {appt['end_time'].strftime('%I:%M %p')} (Priority: {appt['priority']})"
        )

    print("\n===== END TEST DATA =====\n")

    # Initialize calendar tool and set active calendar
    calendar = CalendarTool(calendar_service)
    calendar.set_active_calendar(calendar_id)
    logger.info(f"Set active calendar to {calendar_id}")

    # Initialize agent dependencies with a persistent conversation history
    conversation_history = []  # Store conversation history

    # Pre-load existing appointments into the conversation history
    # This helps the agent be aware of appointments even without them being mentioned
    # Instead of using test_appointments directly, get the actual appointments from the database
    # which will include their IDs
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    # Get today's and tomorrow's appointments from the database
    success, db_appointments = calendar_service.get_appointments_in_range(
        calendar_id=calendar_id, start_time=today, end_time=tomorrow + timedelta(days=1)
    )

    # Create dependencies with the persistent context
    deps = CalendarDependencies(
        calendar=calendar,
        conversation_history=conversation_history,
    )

    logger.info("Starting Calendar Agent Chat Interface")
    print("Type 'exit' to quit")
    print("\nExample queries:")
    print("- Schedule a client meeting today at 10 AM")
    print("- Find me a 30-minute slot between 2 PM and 5 PM tomorrow")
    print("- Need to show 456 Luxury Lane 9am-12pm today, high priority!!")
    print()

    while True:
        try:
            # Get user input with a consistent prompt
            user_input = input("You> ").strip()

            # Skip empty inputs
            if not user_input:
                continue

            if user_input.lower() == "exit":
                logger.info("User requested exit")
                break

            # Add user message to history
            conversation_history.append(Message(role="user", content=user_input))

            # Update the conversation history in deps
            deps.conversation_history = conversation_history

            # Update the system prompt with current context
            calendar_agent.system_prompt = get_system_prompt(conversation_history)

            # Log the current context
            conversation_context_str = get_conversation_context(conversation_history)
            logger.debug(f"Conversation context: {conversation_context_str}")

            # Process with the agent
            logger.debug(f"Processing user input: {user_input}")

            result = await run_with_calendar(
                prompt=user_input,
                history=conversation_history,
                calendar_service=calendar_service,
                calendar_id=calendar_id,
            )

            # Add assistant response to history
            conversation_history.append(
                Message(role="assistant", content=result.data.message)
            )

            # Display response
            print("\nAssistant:", result.data.message)

            # If it's a calendar response, show additional details
            if result.data.type == "CALENDAR":
                if result.data.suggested_slots:
                    print("\nSuggested time slots:")
                    for slot in result.data.suggested_slots:
                        print(
                            f"- {slot.start_time.strftime('%Y-%m-%d %H:%M')} to {slot.end_time.strftime('%H:%M')}"
                        )

                if result.data.conflicts:
                    print("\nConflicting appointments:")
                    for conflict in result.data.conflicts:
                        print(f"- {conflict['title']} at {conflict['start_time']}")

                if result.data.action_taken:
                    print("\nAction taken:", result.data.action_taken)

            print()  # Empty line for readability

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error processing request\n{e}")
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
