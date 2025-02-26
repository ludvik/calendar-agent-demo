import asyncio
from datetime import datetime, timedelta

from agent import calendar_agent, CalendarDependencies
from calendar_tool import CalendarTool


async def main():
    # Initialize dependencies
    calendar = CalendarTool()
    deps = CalendarDependencies(calendar=calendar)

    print("Calendar Agent Chat Interface")
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
            if user_input.lower() == "exit":
                break

            # Process with the agent
            result = await calendar_agent.run(user_input, deps=deps)

            # Display response
            print("\nAssistant:", result.data.message)

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
            break
        except Exception as e:
            print(f"Error: {e}")
            continue


if __name__ == "__main__":
    asyncio.run(main())
