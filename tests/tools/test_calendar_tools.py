"""Tests for calendar tools."""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import RunContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.agent import (
    CalendarDependencies,
    CalendarResponse,
    Message,
    batch_update,
    cancel_appointment,
    check_availability,
    check_day_availability,
    find_available_time_slots,
    schedule_appointment,
)
from calendar_agent.calendar_service import CalendarService
from calendar_agent.calendar_tool import Appointment, AppointmentStatus, CalendarTool
from calendar_agent.models import Appointment, Base, Calendar


@pytest.fixture
def db_session():
    """Create a test database and session."""
    # Use an in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    Base.metadata.create_all(engine)

    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    # Clean up
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def calendar_service(db_session):
    """Create a calendar service with test database session."""
    return CalendarService(lambda: db_session)


@pytest.fixture
def calendar_tool(calendar_service):
    """Create a calendar tool with the calendar service."""
    return CalendarTool(calendar_service)


@pytest.fixture
def test_calendar(calendar_service):
    """Create a test calendar."""
    return calendar_service.create_calendar(
        agent_id="test_agent", name="Test Calendar", time_zone="UTC"
    )


@pytest.fixture
def mock_run_context(calendar_tool, calendar_service):
    """Create a mock RunContext with CalendarDependencies."""
    # Create a mock RunContext
    mock_ctx = MagicMock(spec=RunContext)

    # Set up the deps attribute with CalendarDependencies
    mock_ctx.deps = CalendarDependencies(
        calendar=calendar_tool,
        calendar_service=calendar_service,
        conversation_history=[],
    )

    return mock_ctx


@pytest.mark.asyncio
async def test_schedule_appointment_success(
    mock_run_context, test_calendar, calendar_service
):
    """Test scheduling an appointment successfully."""
    # Prepare test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)

    # Call the agent's schedule_appointment function
    response = await schedule_appointment(
        ctx=mock_run_context,
        calendar_id=test_calendar.id,
        title="Test Meeting",
        start_time=start_time,
        duration=60,
        priority=3,
        description="Test description",
        location="Test location",
    )

    # Verify the response
    assert isinstance(response, CalendarResponse)
    assert response.type == "CALENDAR"
    assert "Successfully scheduled" in response.message
    assert "Test Meeting" in response.message
    assert response.conflicts is None

    # Verify the appointment in the database
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        assert len(appointments) == 1
        assert appointments[0].title == "Test Meeting"
        assert appointments[0].status == AppointmentStatus.CONFIRMED
        assert appointments[0].priority == 3
        assert appointments[0].description == "Test description"
        assert appointments[0].location == "Test location"


@pytest.mark.asyncio
async def test_schedule_appointment_conflict(
    mock_run_context, test_calendar, calendar_service
):
    """Test scheduling an appointment with a conflict."""
    # Prepare test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    # Create an existing appointment
    existing_appointment = Appointment(
        calendar_id=test_calendar.id,
        title="Existing Meeting",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=2,  # Higher priority (lower number)
    )

    with calendar_service.session_factory() as session:
        session.add(existing_appointment)
        session.commit()
        session.refresh(existing_appointment)

    # Call the agent's schedule_appointment function
    response = await schedule_appointment(
        ctx=mock_run_context,
        calendar_id=test_calendar.id,
        title="New Meeting",
        start_time=start_time,
        duration=60,
        priority=3,  # Lower priority (higher number)
        description="Test description",
        location="Test location",
    )

    # Verify the response
    assert isinstance(response, CalendarResponse)
    assert response.type == "CALENDAR"
    assert "not available" in response.message
    assert "Failed" in response.action_taken

    # Verify that conflicts list contains the conflicting appointment
    assert response.conflicts is not None
    assert len(response.conflicts) == 1
    conflict = response.conflicts[0]
    assert conflict["title"] == "Existing Meeting"
    assert conflict["priority"] == 2
    assert conflict["status"] == "CONFIRMED"

    # Verify that the existing appointment is still in the database
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        assert len(appointments) == 1
        assert appointments[0].title == "Existing Meeting"
        assert appointments[0].priority == 2


@pytest.mark.asyncio
async def test_schedule_appointment_with_lower_priority_conflict(
    mock_run_context, test_calendar, calendar_service
):
    """Test scheduling an appointment with a lower priority conflict."""
    # Prepare test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    # Create an existing appointment with lower priority
    existing_appointment = Appointment(
        calendar_id=test_calendar.id,
        title="Existing Meeting",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=4,  # Lower priority (higher number)
    )

    with calendar_service.session_factory() as session:
        session.add(existing_appointment)
        session.commit()
        session.refresh(existing_appointment)

    # Store the existing appointment ID for later verification
    existing_appointment_id = existing_appointment.id

    # Call the agent's schedule_appointment function
    response = await schedule_appointment(
        ctx=mock_run_context,
        calendar_id=test_calendar.id,
        title="Important Meeting",
        start_time=start_time,
        duration=60,
        priority=2,  # Higher priority (lower number)
        description="Test description",
        location="Test location",
    )

    # Verify the response
    assert isinstance(response, CalendarResponse)
    assert response.type == "CALENDAR"
    assert "Successfully scheduled" in response.message
    assert "Important Meeting" in response.message
    assert response.conflicts is not None
    assert len(response.conflicts) == 1
    conflict = response.conflicts[0]
    assert conflict["title"] == "Existing Meeting"
    assert conflict["priority"] == 4

    with calendar_service.session_factory() as session:
        # First verify that both appointments exist
        all_appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        assert len(all_appointments) == 2

        # Verify the new appointment was created successfully
        new_appointment = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id,
                Appointment.title == "Important Meeting",
            )
            .first()
        )
        assert new_appointment is not None
        assert new_appointment.title == "Important Meeting"
        assert new_appointment.priority == 2
        assert new_appointment.description == "Test description"
        assert new_appointment.location == "Test location"

        # Verify the existing appointment remains unchanged
        old_appointment = (
            session.query(Appointment)
            .filter(Appointment.id == existing_appointment_id)
            .first()
        )
        assert old_appointment is not None
        assert old_appointment.title == "Existing Meeting"
        assert old_appointment.priority == 4
        assert old_appointment.status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_check_availability_available(
    mock_run_context, test_calendar, calendar_service
):
    """Test checking availability when the time slot is available."""
    # Prepare test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)

    # Call the agent's check_availability function
    response = await check_availability(
        ctx=mock_run_context,
        calendar_id=test_calendar.id,
        time=start_time,
        duration=60,
    )

    # Verify the response
    assert isinstance(response, CalendarResponse)
    assert response.type == "CALENDAR"
    assert "available" in response.message
    assert "2:00 PM" in response.message
    assert "Checked availability" in response.action_taken

    # Verify no appointments exist in the database
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        assert len(appointments) == 0


@pytest.mark.asyncio
async def test_check_availability_not_available(
    mock_run_context, test_calendar, calendar_service
):
    """Test checking availability when the time slot is not available."""
    # Prepare test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    # Create an existing appointment
    existing_appointment = Appointment(
        calendar_id=test_calendar.id,
        title="Existing Meeting",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=3,
    )

    with calendar_service.session_factory() as session:
        session.add(existing_appointment)
        session.commit()
        session.refresh(existing_appointment)

    # Call the agent's check_availability function
    response = await check_availability(
        ctx=mock_run_context,
        calendar_id=test_calendar.id,
        time=start_time,
        duration=60,
    )

    # Verify the response
    assert isinstance(response, CalendarResponse)
    assert response.type == "CALENDAR"
    assert "not available" in response.message
    assert "2:00 PM" in response.message
    assert "Checked availability" in response.action_taken

    # Verify the appointment exists in the database
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        assert len(appointments) == 1
        assert appointments[0].title == "Existing Meeting"
        assert appointments[0].status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_find_available_time_slots_success(mock_run_context, test_calendar, calendar_service):
    """Test find_available_time_slots when time slots are available."""
    # Setup test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=12, minute=0, second=0, microsecond=0)

    # Call the function
    result = await find_available_time_slots(
        mock_run_context,
        calendar_id=test_calendar.id,
        start_time=start_time,
        end_time=end_time,
        duration=60,
        count=3,
    )

    # Verify the result using the correct CalendarResponse properties
    assert "Found" in result.message
    assert "available time slots" in result.message
    assert result.suggested_slots is not None
    assert len(result.suggested_slots) > 0


@pytest.mark.asyncio
async def test_find_available_time_slots_empty(mock_run_context, test_calendar, calendar_service):
    """Test find_available_time_slots when no time slots are available."""
    # Setup test data
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
    
    # Create appointments for the entire time range to ensure no slots are available
    for hour in range(10, 12):
        appointment = Appointment(
            calendar_id=test_calendar.id,
            title=f"Existing Meeting at {hour}",
            start_time=start_time.replace(hour=hour),
            end_time=start_time.replace(hour=hour+1),
            status=AppointmentStatus.CONFIRMED,
            priority=3,
        )
        
        with calendar_service.session_factory() as session:
            session.add(appointment)
            session.commit()

    # Call the function
    result = await find_available_time_slots(
        mock_run_context,
        calendar_id=test_calendar.id,
        start_time=start_time,
        end_time=end_time,
        duration=60,
        count=3,
    )

    # Verify the result using the correct CalendarResponse properties
    assert "Found 0 available time slots" in result.message
    assert result.suggested_slots is not None
    assert len(result.suggested_slots) == 0


@pytest.mark.asyncio
async def test_find_available_time_slots_missing_params(mock_run_context):
    """Test find_available_time_slots with missing parameters."""
    # Call the function with missing parameters
    result = await find_available_time_slots(
        mock_run_context, calendar_id=None, start_time=None, end_time=None
    )

    # Verify the result using the correct CalendarResponse properties
    assert "Missing required parameters" in result.message
    assert result.suggested_slots is None


@pytest.mark.asyncio
async def test_check_day_availability_free(mock_run_context, test_calendar, calendar_service):
    """Test check_day_availability when the day is completely free."""
    # Get the test calendar
    calendar = test_calendar

    # Use tomorrow's date to avoid conflicts with other tests
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    
    # Call the function
    result = await find_available_time_slots(
        mock_run_context,
        calendar_id=calendar.id,
        start_time=tomorrow,
        end_time=tomorrow + timedelta(hours=8),
        duration=30,
    )
    
    # Call the check_day_availability function
    response = await check_day_availability(
        mock_run_context,
        calendar_id=calendar.id,
        date=tomorrow,
    )
    
    # Verify the response
    assert response.message.startswith("The entire day from")
    assert "is available" in response.message
    assert response.action_taken == "Found: Day is completely free"
    assert response.suggested_slots is None


@pytest.mark.asyncio
async def test_check_day_availability_with_appointments(mock_run_context, test_calendar, calendar_service):
    """Test check_day_availability when there are appointments on the day."""
    # Get the test calendar
    calendar = test_calendar

    # Use day after tomorrow to avoid conflicts with other tests
    day_after_tomorrow = datetime.now(timezone.utc) + timedelta(days=2)
    
    # Create a test appointment
    start_time = datetime.combine(day_after_tomorrow.date(), time(10, 0)).replace(tzinfo=timezone.utc)
    end_time = datetime.combine(day_after_tomorrow.date(), time(11, 0)).replace(tzinfo=timezone.utc)
    
    # Schedule an appointment
    appointment = Appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=1,
    )
    
    # Use session_factory() with a context manager as done in other tests
    with calendar_service.session_factory() as session:
        session.add(appointment)
        session.commit()
    
    # Call the check_day_availability function
    response = await check_day_availability(
        mock_run_context,
        calendar_id=calendar.id,
        date=day_after_tomorrow,
    )
    
    # Verify the response
    assert "Busy times" in response.message
    assert "Test Appointment" in response.message
    assert response.action_taken == "Found 1 appointments"
    assert response.suggested_slots is None
    
    # Clean up
    with calendar_service.session_factory() as session:
        session.delete(appointment)
        session.commit()


@pytest.mark.asyncio
async def test_batch_update_success(mock_run_context, test_calendar, calendar_service):
    """Test batch_update with successful updates."""
    # Get the test calendar
    calendar = test_calendar

    # Create test appointments
    now = datetime.now(timezone.utc)
    
    # Create two appointments
    appointments = []
    for i in range(2):
        start_time = now + timedelta(days=i+3, hours=10)  # Start at 10 AM
        end_time = now + timedelta(days=i+3, hours=11)    # End at 11 AM
        
        appointment = Appointment(
            calendar_id=calendar.id,
            title=f"Test Appointment {i+1}",
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.CONFIRMED,
            priority=3,
        )
        
        with calendar_service.session_factory() as session:
            session.add(appointment)
            session.commit()
            appointment_id = appointment.id
            appointments.append(appointment_id)
    
    # Create batch update operations
    updates = [
        {
            "appointment_id": appointments[0],
            "title": "Updated Appointment 1",
            "priority": 2,
        },
        {
            "appointment_id": appointments[1],
            "title": "Updated Appointment 2",
            "start_time": now + timedelta(days=4, hours=14),  # Change to 2 PM
            "end_time": now + timedelta(days=4, hours=15),    # Change to 3 PM
        },
    ]
    
    # Call batch_update
    response = await batch_update(mock_run_context, updates)
    
    # Verify response
    assert response.type == "CALENDAR"
    assert "Successfully updated 2 appointments" in response.message
    assert response.action_taken == "Batch updated 2 appointments"
    
    # Verify the appointments were actually updated
    with calendar_service.session_factory() as session:
        # Check first appointment
        appt1 = session.query(Appointment).filter_by(id=appointments[0]).first()
        assert appt1.title == "Updated Appointment 1"
        assert appt1.priority == 2
        
        # Check second appointment
        appt2 = session.query(Appointment).filter_by(id=appointments[1]).first()
        assert appt2.title == "Updated Appointment 2"
        assert appt2.start_time.hour == (now + timedelta(days=4, hours=14)).hour
        assert appt2.end_time.hour == (now + timedelta(days=4, hours=15)).hour
    
    # Clean up
    with calendar_service.session_factory() as session:
        for appointment_id in appointments:
            appointment = session.query(Appointment).filter_by(id=appointment_id).first()
            if appointment:
                session.delete(appointment)
        session.commit()


@pytest.mark.asyncio
async def test_batch_update_partial_failure(mock_run_context, test_calendar, calendar_service):
    """Test batch_update with some failed updates."""
    # Get the test calendar
    calendar = test_calendar

    # Create a test appointment
    now = datetime.now(timezone.utc)
    start_time = now + timedelta(days=5, hours=10)  # Start at 10 AM
    end_time = now + timedelta(days=5, hours=11)    # End at 11 AM
    
    appointment = Appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=3,
    )
    
    with calendar_service.session_factory() as session:
        session.add(appointment)
        session.commit()
        appointment_id = appointment.id
    
    # Create batch update operations with one valid and one invalid
    updates = [
        {
            "appointment_id": appointment_id,
            "title": "Updated Appointment",
            "priority": 2,
        },
        {
            "appointment_id": 9999,  # Non-existent appointment ID
            "title": "This should fail",
        },
    ]
    
    # Call batch_update
    response = await batch_update(mock_run_context, updates)
    
    # Verify response
    assert response.type == "CALENDAR"
    assert "Partially successful" in response.message
    assert "1 updates failed" in response.message
    
    # Verify the valid appointment was updated
    with calendar_service.session_factory() as session:
        appt = session.query(Appointment).filter_by(id=appointment_id).first()
        assert appt.title == "Updated Appointment"
        assert appt.priority == 2
    
    # Clean up
    with calendar_service.session_factory() as session:
        appointment = session.query(Appointment).filter_by(id=appointment_id).first()
        if appointment:
            session.delete(appointment)
        session.commit()


@pytest.mark.asyncio
async def test_batch_update_empty(mock_run_context):
    """Test batch_update with empty updates list."""
    # Call batch_update with empty list
    response = await batch_update(mock_run_context, [])
    
    # Verify response
    assert response.type == "CALENDAR"
    assert "No updates provided" in response.message
    assert response.action_taken == "No action taken"


@pytest.mark.asyncio
async def test_cancel_appointment_success(mock_run_context, test_calendar, calendar_service):
    """Test cancel_appointment with a valid appointment."""
    # Get the test calendar
    calendar = test_calendar

    # Create a test appointment
    now = datetime.now(timezone.utc)
    start_time = now + timedelta(days=1, hours=10)  # Start at 10 AM tomorrow
    end_time = now + timedelta(days=1, hours=11)    # End at 11 AM tomorrow
    
    appointment = Appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        priority=3,
    )
    
    with calendar_service.session_factory() as session:
        session.add(appointment)
        session.commit()
        appointment_id = appointment.id
    
    # Call cancel_appointment
    response = await cancel_appointment(mock_run_context, calendar.id, appointment_id)
    
    # Verify response
    assert response.type == "CALENDAR"
    assert "Successfully cancelled appointment" in response.message
    assert "Test Appointment" in response.message
    assert response.action_taken.startswith("Cancelled:")
    
    # Verify the appointment was actually cancelled
    with calendar_service.session_factory() as session:
        updated_appointment = session.query(Appointment).filter_by(id=appointment_id).first()
        assert updated_appointment.status == AppointmentStatus.CANCELLED
    
    # Clean up
    with calendar_service.session_factory() as session:
        session.delete(updated_appointment)
        session.commit()


@pytest.mark.asyncio
async def test_cancel_appointment_not_found(mock_run_context, test_calendar):
    """Test cancel_appointment with a non-existent appointment."""
    # Use a non-existent appointment ID
    non_existent_id = 9999
    
    # Call cancel_appointment
    response = await cancel_appointment(mock_run_context, test_calendar.id, non_existent_id)
    
    # Verify response
    assert response.type == "CALENDAR"
    assert "Appointment not found" in response.message
    assert response.action_taken == "Failed: Appointment not found"
