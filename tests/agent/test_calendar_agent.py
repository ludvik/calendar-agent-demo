from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.agent import Message, run_with_calendar_sync
from calendar_agent.calendar_service import CalendarService
from calendar_agent.calendar_tool import CalendarTool
from calendar_agent.config import DatabaseConfig
from calendar_agent.models import Appointment, AppointmentStatus, Base, Calendar


@pytest.fixture
def db_session():
    """Create a test database and session."""
    # Use an in-memory SQLite database for testing
    db_config = DatabaseConfig("sqlite:///:memory:")
    engine = db_config.engine

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
def test_calendar(calendar_service):
    """Create a test calendar."""
    return calendar_service.create_calendar(
        agent_id="test_agent", name="Test Calendar", time_zone="UTC"
    )


def test_schedule_appointment_integration(calendar_service, test_calendar):
    """Test scheduling appointment through natural language."""
    calendar_service.set_active_calendar(test_calendar.id)

    # Natural language request
    prompt = "Schedule a meeting with John tomorrow at 2pm for 1 hour"
    history = [Message(role="user", content=prompt)]

    # Process through agent
    response = run_with_calendar_sync(prompt, history, calendar_service, test_calendar.id)

    # Verify tool response structure
    assert response.data.type == "CALENDAR"
    assert response.data.action_taken.startswith("Scheduled:")
    assert response.data.suggested_slots is None

    # Verify database state with concrete values
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )

        assert len(appointments) == 1
        apt = appointments[0]

        # Verify exact appointment properties
        assert apt.calendar_id == test_calendar.id
        assert apt.title == "Meeting with John"
        assert apt.start_time.hour == 14  # 2 PM
        assert apt.end_time.hour == 15    # 3 PM
        assert apt.status == AppointmentStatus.CONFIRMED
        assert isinstance(apt.created_at, datetime)


def test_check_availability_integration(calendar_service, test_calendar):
    """Test checking availability through natural language."""
    # Schedule a meeting first
    calendar_service.set_active_calendar(test_calendar.id)
    start_time = datetime(2025, 2, 26, 14, 0, tzinfo=timezone.utc)  # 2 PM
    end_time = start_time + timedelta(hours=1)
    success, _ = calendar_service.schedule_appointment(
        calendar_id=test_calendar.id,
        title="Existing Meeting",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
    )
    assert success

    # Natural language request
    prompt = "Check if 2pm tomorrow is available"
    history = [Message(role="user", content=prompt)]

    # Process through agent
    response = run_with_calendar_sync(prompt, history, calendar_service, test_calendar.id)

    # Verify tool response structure
    assert response.data.type == "CALENDAR"
    assert response.data.action_taken.startswith("Checked availability")
    assert response.data.suggested_slots is None
    
    # Verify the time is actually not available in the database
    with calendar_service.session_factory() as session:
        conflicts = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id,
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.start_time <= start_time,
                Appointment.end_time >= end_time,
            )
            .all()
        )
        assert len(conflicts) == 1


def test_find_free_slots_integration(calendar_service, test_calendar):
    """Test finding free slots through natural language."""
    calendar_service.set_active_calendar(test_calendar.id)

    # Natural language request
    prompt = "When am I free tomorrow afternoon?"
    history = [Message(role="user", content=prompt)]

    # Process through agent
    response = run_with_calendar_sync(prompt, history, calendar_service, test_calendar.id)

    # Verify tool response structure
    assert response.data.type == "CALENDAR"
    assert response.data.action_taken.startswith("Found available slots")
    assert isinstance(response.data.suggested_slots, list)
    
    # Verify each suggested slot is actually available in the database
    if response.data.suggested_slots:
        with calendar_service.session_factory() as session:
            for start, end in response.data.suggested_slots:
                conflicts = (
                    session.query(Appointment)
                    .filter(
                        Appointment.calendar_id == test_calendar.id,
                        Appointment.status == AppointmentStatus.CONFIRMED,
                        Appointment.start_time < end,
                        Appointment.end_time > start,
                    )
                    .all()
                )
                assert len(conflicts) == 0
