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
    run,
)
from .calendar_service import CalendarService
from .config import DatabaseConfig
from .models import Appointment, AppointmentStatus, Calendar


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
        # Next week's appointments (Monday to Friday)
        # Monday - Busy day
        {
            "title": "Team Planning Session",
            "start_time": today.replace(hour=9, minute=0) + timedelta(days=3),  # Monday
            "end_time": today.replace(hour=11, minute=0) + timedelta(days=3),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 2,
            "type": "internal",
            "description": "Quarterly planning session",
            "location": "Main Conference Room",
        },
        {
            "title": "Client Lunch - VIP Investor",
            "start_time": today.replace(hour=12, minute=0) + timedelta(days=3),  # Monday
            "end_time": today.replace(hour=13, minute=30) + timedelta(days=3),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 1,
            "type": "client_meeting",
            "description": "Lunch with potential investor",
            "location": "Luxury Restaurant",
        },
        {
            "title": "Property Tour - Luxury Condos",
            "start_time": today.replace(hour=14, minute=0) + timedelta(days=3),  # Monday
            "end_time": today.replace(hour=16, minute=0) + timedelta(days=3),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 2,
            "type": "client_meeting",
            "description": "Tour of new luxury condo development",
            "location": "Downtown Development",
        },
        # Tuesday - Medium busy
        {
            "title": "Sales Team Meeting",
            "start_time": today.replace(hour=10, minute=0) + timedelta(days=4),  # Tuesday
            "end_time": today.replace(hour=11, minute=0) + timedelta(days=4),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,
            "type": "internal",
            "description": "Weekly sales team sync",
            "location": "Office",
        },
        {
            "title": "Property Showing - 789 Pine St",
            "start_time": today.replace(hour=14, minute=0) + timedelta(days=4),  # Tuesday
            "end_time": today.replace(hour=15, minute=0) + timedelta(days=4),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 2,
            "type": "client_meeting",
            "description": "Show property to potential buyers",
            "location": "789 Pine St",
        },
        # Wednesday - Least busy
        {
            "title": "Quick Check-in Call",
            "start_time": today.replace(hour=9, minute=0) + timedelta(days=5),  # Wednesday
            "end_time": today.replace(hour=9, minute=30) + timedelta(days=5),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 4,
            "type": "internal",
            "description": "Brief team check-in",
            "location": "Phone",
        },
        # Thursday - Medium busy
        {
            "title": "Marketing Review",
            "start_time": today.replace(hour=11, minute=0) + timedelta(days=6),  # Thursday
            "end_time": today.replace(hour=12, minute=30) + timedelta(days=6),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,
            "type": "internal",
            "description": "Review marketing materials",
            "location": "Office",
        },
        {
            "title": "Property Inspection",
            "start_time": today.replace(hour=14, minute=0) + timedelta(days=6),  # Thursday
            "end_time": today.replace(hour=15, minute=30) + timedelta(days=6),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 2,
            "type": "client_meeting",
            "description": "Final inspection before listing",
            "location": "555 Maple Ave",
        },
        # Friday - Somewhat busy
        {
            "title": "Team Lunch",
            "start_time": today.replace(hour=12, minute=0) + timedelta(days=7),  # Friday
            "end_time": today.replace(hour=13, minute=30) + timedelta(days=7),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,
            "type": "internal",
            "description": "Team building lunch",
            "location": "Local Restaurant",
        },
        {
            "title": "Weekly Report Preparation",
            "start_time": today.replace(hour=15, minute=0) + timedelta(days=7),  # Friday
            "end_time": today.replace(hour=16, minute=30) + timedelta(days=7),
            "status": AppointmentStatus.CONFIRMED,
            "priority": 3,
            "type": "internal",
            "description": "Prepare weekly reports",
            "location": "Office",
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
    
    # Next week appointments (Monday to Friday)
    next_week_appts = [
        a
        for a in test_appointments
        if a["start_time"].date() >= (today + timedelta(days=3)).date() and 
           a["start_time"].date() <= (today + timedelta(days=7)).date()
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
    
    # Group next week appointments by day
    next_week_by_day = {}
    for appt in next_week_appts:
        day = appt["start_time"].strftime('%A, %Y-%m-%d')
        if day not in next_week_by_day:
            next_week_by_day[day] = []
        next_week_by_day[day].append(appt)
    
    print("\nNext Week's Appointments:")
    for day, appts in next_week_by_day.items():
        print(f"\n  {day}:")
        for i, appt in enumerate(appts, 1):
            print(
                f"  {i}. {appt['title']} - {appt['start_time'].strftime('%I:%M %p')} to {appt['end_time'].strftime('%I:%M %p')} (Priority: {appt['priority']})"
            )

    print("\n===== END TEST DATA =====\n")

    # Initialize calendar service
    logger.info(f"Using calendar ID: {calendar_id}")

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
        calendar_service=calendar_service,
        conversation_history=conversation_history,
    )

    logger.info("Starting Calendar Agent Chat Interface")
    print("Type 'exit' to quit")
    print("\nExample queries:")
    print(
        "- Schedule a condo viewing at 123 Main St for tomorrow 2-3pm (Basic Appointment Scheduling)"
    )
    print(
        "- Need to show 456 Luxury Lane today 3-5pm. This is high priority! (Priority Conflict Resolution)"
    )
    print(
        "- Find me 3 available 1-hour slots for a client meeting today or tomorrow? (Propose Available Time Slots)"
    )
    print(
        "- Which day next week is least busy so I can schedule some prospecting calls? (Identify Underutilized Days)"
    )
    print(
        "- Could you help cancel this blocking marketing meeting? It is only an internal meeting (Context-Aware Appointment Management)"
    )
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

            result = await run(
                user_prompt=user_input,
                history=conversation_history,
                calendar_service=calendar_service,
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
                            f"- {slot.start_time} to {slot.end_time}"
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
        except EOFError:
            # Handle EOF (end of file) when input is piped from another command
            logger.info("EOF received, exiting")
            break
        except Exception as e:
            logger.error(f"Error processing request\n{e}")
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
