"""
Test script for batch_update tool.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Any

from calendar_agent.agent import (
    AppointmentStatus,
    CalendarResponse,
)
from calendar_agent.calendar_service import CalendarService
from calendar_agent.calendar_tool import CalendarTool
from calendar_agent.models import Appointment, AppointmentStatus, Base, Calendar
from calendar_agent.config import DatabaseConfig


@pytest.mark.asyncio
async def test_batch_update():
    """Test the batch_update functionality directly."""
    # Use an in-memory SQLite database for testing
    db_config = DatabaseConfig("sqlite:///:memory:")
    engine = db_config.engine
    
    # Create tables
    Base.metadata.create_all(engine)
    
    # Create a session
    session = db_config.session_factory()
    
    # Create a calendar service
    calendar_service = CalendarService(session_factory=db_config.session_factory)
    
    # Create a calendar
    calendar = Calendar(name="Test Calendar", agent_id="test_agent")
    session.add(calendar)
    session.commit()
    
    # Create a calendar tool
    calendar_tool = CalendarTool(calendar_service=calendar_service)
    calendar_tool.set_active_calendar(calendar.id)
    
    # Create some appointments
    now = datetime.now(timezone.utc)
    appointments = []
    
    # Appointment 1: High priority meeting
    appt1 = Appointment(
        title="High Priority Meeting",
        start_time=now + timedelta(days=1, hours=10),
        end_time=now + timedelta(days=1, hours=11),
        status=AppointmentStatus.CONFIRMED,
        priority=1,
        calendar_id=calendar.id,
    )
    session.add(appt1)
    
    # Appointment 2: Regular client meeting
    appt2 = Appointment(
        title="Client Meeting",
        start_time=now + timedelta(days=1, hours=14),
        end_time=now + timedelta(days=1, hours=15),
        status=AppointmentStatus.CONFIRMED,
        priority=3,
        calendar_id=calendar.id,
    )
    session.add(appt2)
    
    # Appointment 3: Office maintenance
    appt3 = Appointment(
        title="Office Maintenance",
        start_time=now + timedelta(days=2, hours=9),
        end_time=now + timedelta(days=2, hours=12),
        status=AppointmentStatus.CONFIRMED,
        priority=4,
        calendar_id=calendar.id,
    )
    session.add(appt3)
    
    session.commit()
    
    # Test batch update functionality directly using the calendar tool
    print("Testing batch update functionality directly:")
    
    # Reschedule appointment 1
    print("\nRescheduling appointment 1:")
    success1, updated1, conflicts1 = calendar_tool.update_appointment(
        appointment_id=appt1.id,
        start_time=now + timedelta(days=1, hours=11),
        end_time=now + timedelta(days=1, hours=12),
    )
    print(f"Success: {success1}")
    print(f"Updated: {updated1}")
    print(f"Conflicts: {conflicts1}")
    
    # Cancel appointment 2
    print("\nCancelling appointment 2:")
    success2, updated2, conflicts2 = calendar_tool.update_appointment(
        appointment_id=appt2.id,
        status=AppointmentStatus.CANCELLED,
    )
    print(f"Success: {success2}")
    print(f"Updated: {updated2}")
    print(f"Conflicts: {conflicts2}")
    
    # Change priority and location of appointment 3
    print("\nChanging priority and location of appointment 3:")
    success3, updated3, conflicts3 = calendar_tool.update_appointment(
        appointment_id=appt3.id,
        priority=2,
        location="Main Office",
    )
    print(f"Success: {success3}")
    print(f"Updated: {updated3}")
    print(f"Conflicts: {conflicts3}")
    
    # Verify the changes by retrieving the appointments
    print("\nVerifying changes using calendar_tool:")
    
    # Get appointment 1
    appt1_updated = calendar_tool.get_appointment(appt1.id)
    print(f"Appointment 1 (Rescheduled):")
    print(f"  - Title: {appt1_updated.get('title')}")
    print(f"  - Start Time: {appt1_updated.get('start_time')}")
    print(f"  - End Time: {appt1_updated.get('end_time')}")
    print(f"  - Status: {appt1_updated.get('status')}")
    
    # Get appointment 2
    appt2_updated = calendar_tool.get_appointment(appt2.id)
    print(f"\nAppointment 2 (Cancelled):")
    print(f"  - Title: {appt2_updated.get('title')}")
    print(f"  - Status: {appt2_updated.get('status')}")
    
    # Get appointment 3
    appt3_updated = calendar_tool.get_appointment(appt3.id)
    print(f"\nAppointment 3 (Priority & Location Changed):")
    print(f"  - Title: {appt3_updated.get('title')}")
    print(f"  - Priority: {appt3_updated.get('priority')}")
    print(f"  - Location: {appt3_updated.get('location')}")


if __name__ == "__main__":
    asyncio.run(test_batch_update())
