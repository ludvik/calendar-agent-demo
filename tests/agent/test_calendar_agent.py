from datetime import datetime, timedelta, timezone
from time import time
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.agent import (
    CalendarDependencies,
    Message,
    RunContext,
    batch_update,
    calendar_agent,
    run_with_calendar,
    run_with_calendar_sync,
)
from calendar_agent.calendar_service import CalendarService
from calendar_agent.calendar_tool import CalendarTool
from calendar_agent.config import DatabaseConfig
from calendar_agent.models import Appointment, AppointmentStatus, Base, Calendar
from calendar_agent.response import CalendarResponse, ResponseType, TimeSlot


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


@pytest.mark.asyncio
async def test_schedule_appointment_integration(calendar_service, test_calendar):
    """Test scheduling an appointment through natural language."""
    # Natural language request
    prompt = "Schedule a meeting with John tomorrow at 2 PM for 1 hour"
    history = [Message(role="user", content=prompt)]

    # Process through agent using the async version
    result = await run_with_calendar(
        prompt, history, calendar_service, test_calendar.id
    )

    # Verify the result
    assert result is not None

    # Verify appointment details in database
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
        assert apt.end_time.hour == 15  # 3 PM
        assert apt.status == AppointmentStatus.CONFIRMED
        assert isinstance(apt.created_at, datetime)


def test_check_availability_integration(calendar_service, test_calendar):
    """Test checking availability through natural language."""
    # Schedule a meeting first
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    tomorrow_3pm = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
    tomorrow_4pm = tomorrow.replace(hour=16, minute=0, second=0, microsecond=0)

    success, _, _ = calendar_service.schedule_appointment(
        calendar_id=test_calendar.id,
        title="Existing Appointment",
        start_time=tomorrow_3pm,
        end_time=tomorrow_4pm,
        status=AppointmentStatus.CONFIRMED,
    )
    assert success

    # Natural language request
    prompt = "Check if 2pm tomorrow is available"
    history = [Message(role="user", content=prompt)]

    # Process through agent
    response = run_with_calendar_sync(
        prompt, history, calendar_service, test_calendar.id
    )

    # Verify tool response structure
    assert response.data.type == "BASE"
    assert "available" in response.data.message.lower()

    # Verify the time is actually not available in the database
    with calendar_service.session_factory() as session:
        conflicts = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id,
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.start_time <= tomorrow_3pm,
                Appointment.end_time >= tomorrow_4pm,
            )
            .all()
        )
        assert len(conflicts) == 1


def test_find_free_slots_integration(calendar_service, test_calendar):
    """Test finding free slots through natural language."""
    # Natural language request
    prompt = "When am I free tomorrow afternoon?"
    history = [Message(role="user", content=prompt)]

    # Process through agent
    response = run_with_calendar_sync(
        prompt, history, calendar_service, test_calendar.id
    )

    # Verify tool response structure
    assert response.data.type == "BASE"
    assert "available" in response.data.message.lower()

    # Verify each suggested slot is actually available in the database
    if response.data.suggested_slots:
        with calendar_service.session_factory() as session:
            for timeslot in response.data.suggested_slots:
                conflicts = (
                    session.query(Appointment)
                    .filter(
                        Appointment.calendar_id == test_calendar.id,
                        Appointment.status == AppointmentStatus.CONFIRMED,
                        Appointment.start_time < timeslot.end_time,
                        Appointment.end_time > timeslot.start_time,
                    )
                    .all()
                )
                assert len(conflicts) == 0


@pytest.mark.skip(reason="Conflict resolution functionality has been removed")
def test_priority_conflict_resolution_integration(calendar_service, test_calendar):
    """Test priority conflict resolution through LLM interaction (User Story 2)."""
    # 1. Setup existing appointments that will conflict with our high-priority appointment
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    tomorrow_9am = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create an apartment tour at 3:30pm
    apt_tour_start = tomorrow_9am.replace(hour=15, minute=30)
    apt_tour_end = apt_tour_start + timedelta(hours=1)
    apt_tour_success, apt_tour, _ = calendar_service.schedule_appointment(
        calendar_id=test_calendar.id,
        title="Apartment Tour",
        start_time=apt_tour_start,
        end_time=apt_tour_end,
        status=AppointmentStatus.CONFIRMED,
        priority=3,  # Medium priority
    )
    assert apt_tour_success
    apt_tour_id = apt_tour.id

    # Create a team meeting at 4:30pm (after apartment tour ends)
    team_mtg_start = tomorrow_9am.replace(hour=16, minute=30)
    team_mtg_end = team_mtg_start + timedelta(minutes=30)
    team_mtg_success, team_mtg, _ = calendar_service.schedule_appointment(
        calendar_id=test_calendar.id,
        title="Team Meeting",
        start_time=team_mtg_start,
        end_time=team_mtg_end,
        status=AppointmentStatus.CONFIRMED,
        priority=4,  # Lower priority
    )
    assert team_mtg_success
    team_mtg_id = team_mtg.id

    # Create a paperwork review at 5:00pm
    paperwork_start = tomorrow_9am.replace(hour=17, minute=0)
    paperwork_end = paperwork_start + timedelta(minutes=30)
    paperwork_success, paperwork, _ = calendar_service.schedule_appointment(
        calendar_id=test_calendar.id,
        title="Property Paperwork Review",
        start_time=paperwork_start,
        end_time=paperwork_end,
        status=AppointmentStatus.CONFIRMED,
        priority=3,  # Medium priority
    )
    assert paperwork_success
    paperwork_id = paperwork.id

    # Record the initial state of appointments for later comparison
    initial_appointments = {}
    with calendar_service.session_factory() as session:
        appointments = (
            session.query(Appointment)
            .filter(Appointment.calendar_id == test_calendar.id)
            .all()
        )
        for appt in appointments:
            initial_appointments[appt.id] = {
                "title": appt.title,
                "start_time": appt.start_time,
                "end_time": appt.end_time,
                "priority": appt.priority,
                "status": appt.status,
            }

    # 2. Natural language request to schedule a high-priority luxury home viewing
    # that conflicts with existing appointments
    prompt = (
        "I need to schedule a very important luxury home viewing tomorrow from 3 PM to 5 PM. "
        "This is for a VIP client and has high priority. "
        "The property address is 456 Luxury Lane."
    )
    history = [Message(role="user", content=prompt)]

    # 3. Process through agent
    response = run_with_calendar_sync(
        prompt, history, calendar_service, test_calendar.id
    )

    # 4. Verify response type is correct (this is a structured field, not natural language)
    assert response.data.type == "BASE"

    # 5. Find the luxury viewing appointment in the database
    with calendar_service.session_factory() as session:
        # Try different patterns for the luxury viewing title
        luxury_viewing = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id,
                Appointment.title.like("%Luxury%"),
            )
            .first()
        )

        # If not found with "Luxury", try with "VIP"
        if luxury_viewing is None:
            luxury_viewing = (
                session.query(Appointment)
                .filter(
                    Appointment.calendar_id == test_calendar.id,
                    Appointment.title.like("%VIP%"),
                )
                .first()
            )

        # If still not found, try with "456 Luxury Lane"
        if luxury_viewing is None:
            luxury_viewing = (
                session.query(Appointment)
                .filter(
                    Appointment.calendar_id == test_calendar.id,
                    Appointment.title.like("%456%"),
                )
                .first()
            )

        assert (
            luxury_viewing is not None
        ), "Could not find the luxury viewing appointment"
        luxury_id = luxury_viewing.id

        # Verify the luxury viewing appointment has the correct time and high priority
        assert luxury_viewing.start_time.hour == 15  # 3 PM
        assert luxury_viewing.end_time.hour == 17  # 5 PM
        assert luxury_viewing.priority <= 2  # High priority (1 or 2)

    # 6. Simulate user confirming they want to proceed with scheduling
    # and resolving conflicts
    confirm_prompt = (
        "Yes, please schedule it and move any conflicting appointments to the next day. "
        "The team meeting and paperwork review can be in the morning, and the apartment tour "
        "can be at 3 PM the next day."
    )
    history.append(Message(role="assistant", content=response.data.message))
    history.append(Message(role="user", content=confirm_prompt))

    # 7. Process confirmation through agent
    confirm_response = run_with_calendar_sync(
        confirm_prompt, history, calendar_service, test_calendar.id
    )

    # 8. Verify response type is correct (this is a structured field, not natural language)
    assert confirm_response.data.type == "BASE"

    # 9. Verify database state after scheduling
    with calendar_service.session_factory() as session:
        # Verify luxury home viewing is still scheduled
        luxury_viewing = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id, Appointment.id == luxury_id
            )
            .one_or_none()
        )

        assert luxury_viewing is not None
        assert luxury_viewing.start_time.hour == 15  # 3 PM
        assert luxury_viewing.end_time.hour == 17  # 5 PM
        assert luxury_viewing.priority <= 2  # High priority (1 or 2)

        # Verify conflicting appointments were rescheduled
        # and no longer conflict with the luxury viewing
        for appt_id in [apt_tour_id, team_mtg_id, paperwork_id]:
            updated_appt = (
                session.query(Appointment)
                .filter(
                    Appointment.calendar_id == test_calendar.id,
                    Appointment.id == appt_id,
                )
                .one_or_none()
            )

            # Check that the appointment still exists and doesn't conflict
            assert updated_appt is not None, f"Appointment {appt_id} not found"

            # Check that the appointment was actually modified
            initial_state = initial_appointments[appt_id]
            assert (
                updated_appt.start_time != initial_state["start_time"]
                or updated_appt.end_time != initial_state["end_time"]
                or updated_appt.status != initial_state["status"]
            ), f"Appointment {appt_id} was not modified"

            # Check that it doesn't conflict with luxury viewing
            assert (
                updated_appt.end_time <= luxury_viewing.start_time
                or updated_appt.start_time >= luxury_viewing.end_time
            ), f"{updated_appt.title} still conflicts with luxury viewing"

        # Verify no conflicts remain in the calendar
        all_appointments = (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == test_calendar.id,
                Appointment.status == AppointmentStatus.CONFIRMED,
            )
            .all()
        )

        for i, appt1 in enumerate(all_appointments):
            for appt2 in all_appointments[i + 1 :]:
                assert not (
                    appt1.start_time < appt2.end_time
                    and appt1.end_time > appt2.start_time
                ), f"Conflict between {appt1.title} and {appt2.title}"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Conflict resolution functionality has been removed")
async def test_resolve_conflicts_with_type_based_strategies():
    """Test resolving conflicts with type-based strategies."""
    # Create a test database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)

    # Variables to store IDs
    wang_showing_id = None
    internal_meeting1_id = None
    internal_meeting2_id = None
    other_client_id = None
    calendar_id = None

    # Create a calendar
    with session_maker() as session:
        calendar = Calendar(
            name="Test Calendar", time_zone="UTC", agent_id="test-agent"
        )
        session.add(calendar)
        session.commit()
        calendar_id = calendar.id

        # Create a high-priority client meeting (Mrs. Wang's showing)
        wang_showing = Appointment(
            calendar_id=calendar.id,
            title="Property showing with Mrs. Wang",
            description="Client meeting to show the downtown property",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            status=AppointmentStatus.CONFIRMED,
            priority=3,  # High priority
        )
        session.add(wang_showing)

        # Create conflicting internal meetings
        internal_meeting1 = Appointment(
            calendar_id=calendar.id,
            title="Team sync meeting",
            description="Internal team sync",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            status=AppointmentStatus.CONFIRMED,
            priority=2,  # Medium priority
        )
        session.add(internal_meeting1)

        internal_meeting2 = Appointment(
            calendar_id=calendar.id,
            title="Department planning",
            description="Internal planning session",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1, minutes=30),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2, minutes=30),
            status=AppointmentStatus.CONFIRMED,
            priority=2,  # Medium priority
        )
        session.add(internal_meeting2)

        # Create another client meeting that conflicts
        other_client = Appointment(
            calendar_id=calendar.id,
            title="Client consultation",
            description="Meeting with potential buyer",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1, minutes=30),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2, minutes=30),
            status=AppointmentStatus.CONFIRMED,
            priority=3,  # High priority
        )
        session.add(other_client)

        session.commit()

        # Capture IDs before the session closes
        wang_showing_id = wang_showing.id
        internal_meeting1_id = internal_meeting1.id
        internal_meeting2_id = internal_meeting2.id
        other_client_id = other_client.id

    # Create dependencies
    calendar_service = CalendarService(session_maker)
    calendar_tool = CalendarTool(calendar_service)

    # Create natural language prompt for the LLM
    tomorrow_afternoon = (
        (datetime.now(timezone.utc) + timedelta(days=1))
        .replace(hour=14, minute=0, second=0, microsecond=0)
        .strftime("%B %d at %I:%M %p")
    )

    prompt = f"""
    I have several conflicting appointments in my calendar:
    1. A high-priority client meeting with Mrs. Wang for a property showing
    2. Two medium-priority internal team meetings
    3. Another high-priority client consultation
    
    Please resolve these conflicts using these strategies:
    - Cancel all internal meetings
    - Reschedule client meetings to tomorrow afternoon around {tomorrow_afternoon}
    - Keep Mrs. Wang's showing as the highest priority
    """

    # Create conversation history
    history = [Message(role="user", content=prompt)]

    # Run the agent with the natural language prompt using the async version
    result = await run_with_calendar(prompt, history, calendar_service, calendar_id)

    # Print the result object structure for debugging
    print(f"Result type: {type(result)}")
    print(f"Result dir: {dir(result)}")

    # Verify the response
    assert result is not None

    # Check that internal meetings were cancelled
    with session_maker() as session:
        # Check that internal meetings are cancelled
        meeting1 = session.query(Appointment).filter_by(id=internal_meeting1_id).first()
        meeting2 = session.query(Appointment).filter_by(id=internal_meeting2_id).first()
        assert meeting1.status == AppointmentStatus.CANCELLED
        assert meeting2.status == AppointmentStatus.CANCELLED

        # Check that client meetings were rescheduled to tomorrow afternoon
        wang_appt = session.query(Appointment).filter_by(id=wang_showing_id).first()
        other_appt = session.query(Appointment).filter_by(id=other_client_id).first()

        # Due to SQLite timezone issues, we only check hours and minutes
        assert wang_appt.status == AppointmentStatus.CONFIRMED
        assert other_appt.status == AppointmentStatus.CONFIRMED

        # Check that at least one of the client meetings was rescheduled to tomorrow
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        rescheduled_appointments = (
            session.query(Appointment)
            .filter(
                Appointment.start_time >= tomorrow_start,
                Appointment.start_time <= tomorrow_end,
            )
            .all()
        )

        assert len(rescheduled_appointments) > 0
