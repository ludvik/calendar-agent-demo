import asyncio

from loguru import logger

from .agent import (
    CalendarDependencies,
    CalendarResponse,
    Message,
    ResponseType,
    calendar_agent,
)
from .calendar_service import CalendarService
from .calendar_tool import CalendarTool
from .config import DatabaseConfig


async def main():
    # Initialize database and services
    db_config = DatabaseConfig()
    db_config.init_db()
    calendar_service = CalendarService(db_config.session_factory)

    # Create a default calendar if none exists
    session = db_config.session_factory()
    try:
        from .models import Calendar

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

    # Initialize calendar tool and set active calendar
    calendar = CalendarTool(calendar_service)
    calendar.set_active_calendar(calendar_id)
    logger.info(f"Set active calendar to {calendar_id}")

    # Initialize agent dependencies
    deps = CalendarDependencies(calendar=calendar, conversation_history=[])
    conversation_history = []  # Store conversation history

    logger.info("Starting Calendar Agent Chat Interface")
    print("Type 'exit' to quit")
    print("\nExample queries:")
    print("- Find me a 30-minute slot between 2 PM and 5 PM tomorrow")
    print("- Is next Monday wide open?")
    print()

    while True:
        try:
            # Get user input
            user_input = input("You: ")

            if user_input.lower() == "exit":
                logger.info("User requested exit")
                break

            # Add user message to history
            conversation_history.append(Message(role="user", content=user_input))

            # Process with the agent
            logger.debug(f"Processing user input: {user_input}")
            result = await calendar_agent.run(user_input, deps=deps)

            # Add assistant response to history
            conversation_history.append(
                Message(role="assistant", content=result.data.message)
            )

            # Display response
            print("\nA:", result.data.message)

            # Only process calendar-specific fields for CalendarResponse
            if result.data.type == ResponseType.CALENDAR:
                # Show suggested slots if any
                if result.data.suggested_slots:
                    print("\nSuggested time slots:")
                    for slot in result.data.suggested_slots:
                        print(
                            f"- {slot.start_time.strftime('%I:%M %p')} to {slot.end_time.strftime('%I:%M %p')}"
                        )

                # Show action taken if any
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
