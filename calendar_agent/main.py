import asyncio
from datetime import datetime, timedelta

from loguru import logger

from .agent import calendar_agent, CalendarDependencies, CalendarResponse, ResponseType
from .calendar_tool import CalendarTool


async def main():
    # Initialize dependencies
    calendar = CalendarTool()
    deps = CalendarDependencies(calendar=calendar)
    
    logger.info("Starting Calendar Agent Chat Interface")
    print("Type 'exit' to quit")
    print("\nExample queries:")
    print("- Am I free tomorrow at 2 PM?")
    print("- Find me a 30-minute slot between 2 PM and 5 PM tomorrow")
    print("- Is next Monday wide open?")
    print()
    
    while True:
        try:
            # Get user input
            user_input = input("You: ")
            if user_input.lower() == 'exit':
                logger.info("User requested exit")
                break
                
            # Process with the agent
            logger.debug(f"Processing user input: {user_input}")
            result = await calendar_agent.run(user_input, deps=deps)
            
            # Display response
            print("\nA:", result.data.message)
            
            # Only process calendar-specific fields for CalendarResponse
            if result.data.type == ResponseType.CALENDAR:
                # Show suggested slots if any
                if result.data.suggested_slots:
                    print("\nSuggested time slots:")
                    for slot in result.data.suggested_slots:
                        print(f"- {slot.start_time.strftime('%I:%M %p')} to {slot.end_time.strftime('%I:%M %p')}")
                
                # Show action taken if any
                if result.data.action_taken:
                    print("\nAction taken:", result.data.action_taken)
                    logger.info(f"Action taken: {result.data.action_taken}")
            
            print()  # Empty line for readability
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error processing request\n{e}")
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())