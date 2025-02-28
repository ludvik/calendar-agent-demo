"""Tests for calendar tools."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import RunContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.agent import (
    CalendarDependencies,
    CalendarResponse,
    Message,
    check_availability,
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
