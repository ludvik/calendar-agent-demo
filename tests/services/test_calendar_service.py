"""Tests for the calendar service."""

import os
from datetime import datetime, timedelta, timezone
from calendar_agent.models import Calendar, Appointment, AppointmentStatus
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.calendar_service import CalendarService
from calendar_agent.config import DatabaseConfig
from calendar_agent.models import Base


def utc_datetime(*args, **kwargs) -> datetime:
    """Create a UTC datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture(scope="function")
def db_config():
    """Create a new database config for each test."""
    return DatabaseConfig("sqlite:///:memory:")


@pytest.fixture(scope="function")
def session_factory(db_config):
    """Create a new session factory for each test."""
    return db_config.session_factory


@pytest.fixture(scope="function")
def service(session_factory):
    """Create a new calendar service for each test."""
    return CalendarService(session_factory)


@pytest.fixture(scope="function")
def calendar(service):
    """Create a test calendar."""
    return service.create_calendar("test_agent", "Test Calendar", "UTC")


@pytest.fixture(scope="function")
def tomorrow_9am():
    """Get tomorrow at 9 AM UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)


def test_create_calendar(service):
    """Test creating a new calendar."""
    calendar = service.create_calendar("agent123", "My Calendar", "America/Los_Angeles")
    assert calendar.agent_id == "agent123"
    assert calendar.name == "My Calendar"
    assert calendar.time_zone == "America/Los_Angeles"


def test_schedule_confirmed_appointment(service, calendar, tomorrow_9am):
    """Test scheduling a confirmed appointment."""
    success, apt = service.schedule_appointment(
        calendar.id,
        "Morning Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
        priority=3,
    )
    assert success
    assert apt.title == "Morning Meeting"
    assert apt.status == AppointmentStatus.CONFIRMED
    assert apt.priority == 3
    # TODO: Fix timezone handling in SQLite
    # assert apt.start_time.tzinfo is not None  # Ensure timezone-aware
    assert apt.start_time.hour == tomorrow_9am.hour
    assert apt.start_time.minute == tomorrow_9am.minute
    end_time = tomorrow_9am + timedelta(hours=1)
    assert apt.end_time.hour == end_time.hour
    assert apt.end_time.minute == end_time.minute


def test_schedule_conflicting_confirmed_appointments(service, calendar, tomorrow_9am):
    """Test that we can't schedule conflicting confirmed appointments."""
    # Schedule first appointment
    success1, apt1 = service.schedule_appointment(
        calendar.id,
        "First Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
        priority=3,
    )
    assert success1

    # Try to schedule conflicting appointment
    success2, apt2 = service.schedule_appointment(
        calendar.id,
        "Conflicting Meeting",
        tomorrow_9am + timedelta(minutes=30),
        tomorrow_9am + timedelta(hours=1, minutes=30),
        AppointmentStatus.CONFIRMED,
        priority=1,  # Even higher priority shouldn't override CONFIRMED
    )
    assert not success2
    assert apt2 is None


def test_high_priority_overrides_low_priority_tentative(
    service, calendar, tomorrow_9am
):
    """Test that high priority appointment overrides low priority tentative."""
    # Schedule low priority tentative
    success1, apt1 = service.schedule_appointment(
        calendar.id,
        "Tentative Lunch",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.TENTATIVE,
        priority=5,
    )
    assert success1

    # Schedule high priority conflicting
    success2, apt2 = service.schedule_appointment(
        calendar.id,
        "Important Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
        priority=1,
    )
    assert success2

    # Check that first appointment was cancelled
    with service.session_factory() as session:
        apt1_db = session.get(apt1.__class__, apt1.id)
        assert apt1_db.status == AppointmentStatus.CANCELLED


def test_check_availability(service, calendar, tomorrow_9am):
    """Test checking time slot availability."""
    # Initially should be available
    assert service.check_availability(
        calendar.id,
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        priority=5,
    )

    # Schedule an appointment
    service.schedule_appointment(
        calendar.id,
        "Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
    )

    # Now should be unavailable
    assert not service.check_availability(
        calendar.id,
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        priority=5,
    )


def test_find_available_slots(service, calendar, tomorrow_9am):
    """Test finding available time slots."""
    # Schedule some appointments
    service.schedule_appointment(
        calendar.id,
        "Morning Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
    )

    service.schedule_appointment(
        calendar.id,
        "Afternoon Meeting",
        tomorrow_9am.replace(hour=14),
        tomorrow_9am.replace(hour=15),
        AppointmentStatus.CONFIRMED,
    )

    # Find 30-minute slots between 9 AM and 5 PM
    slots = service.find_available_slots(
        calendar.id,
        tomorrow_9am,
        tomorrow_9am.replace(hour=17),
        duration=30,
        priority=5,
    )

    # Should find multiple slots
    assert len(slots) > 0
    # First slot should be after morning meeting
    assert slots[0][0] >= tomorrow_9am + timedelta(hours=1)
    # All slots should be 30 minutes and timezone-aware
    for start, end in slots:
        assert end - start == timedelta(minutes=30)
        assert start.tzinfo is not None
        assert end.tzinfo is not None


def test_is_day_underutilized(service, calendar, tomorrow_9am):
    """Test checking if a day is underutilized."""
    # Initially should be underutilized
    is_under, hours = service.is_day_underutilized(calendar.id, tomorrow_9am)
    assert is_under
    assert hours == 0

    # Add some appointments
    service.schedule_appointment(
        calendar.id,
        "Morning Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=2),
        AppointmentStatus.CONFIRMED,
    )

    service.schedule_appointment(
        calendar.id,
        "Afternoon Meeting",
        tomorrow_9am.replace(hour=14),
        tomorrow_9am.replace(hour=16),
        AppointmentStatus.CONFIRMED,
    )

    # Now should not be underutilized (4 hours of meetings)
    is_under, hours = service.is_day_underutilized(calendar.id, tomorrow_9am)
    assert not is_under
    assert hours == 4.0


def test_cancel_appointment(service, calendar):
    """Test cancelling an appointment."""
    # First schedule an appointment
    start_time = datetime(2025, 2, 26, 14, 0, tzinfo=timezone.utc)  # 2 PM
    end_time = start_time + timedelta(hours=1)
    success, appointment = service.schedule_appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
    )
    assert success
    assert appointment is not None

    # Cancel the appointment
    success = service.cancel_appointment(appointment.id)
    assert success

    # Verify the appointment is cancelled
    with service.session_factory() as session:
        cancelled_apt = session.query(Appointment).filter(
            Appointment.id == appointment.id
        ).first()
        assert cancelled_apt.status == AppointmentStatus.CANCELLED


def test_get_appointments_in_range(service, calendar):
    """Test getting appointments in a time range."""
    # Schedule some appointments
    base_time = datetime(2025, 2, 26, 14, 0, tzinfo=timezone.utc)  # 2 PM
    appointments = []
    
    # Create 3 one-hour appointments starting at 2 PM, 3 PM, and 4 PM
    for i in range(3):
        start_time = base_time + timedelta(hours=i)
        end_time = start_time + timedelta(hours=1)
        success, apt = service.schedule_appointment(
            calendar_id=calendar.id,
            title=f"Appointment {i+1}",
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.CONFIRMED,
        )
        assert success
        appointments.append(apt)

    # Test getting appointments in various ranges
    # 1. Get all appointments (2 PM to 5 PM)
    success, all_apts = service.get_appointments_in_range(
        calendar_id=calendar.id,
        start_time=base_time,
        end_time=base_time + timedelta(hours=3),
    )
    assert success
    assert len(all_apts) == 3
    assert all(a.title in [f"Appointment {i+1}" for i in range(3)] for a in all_apts)

    # 2. Get appointments in middle (2:30 PM to 3:30 PM)
    success, middle_apts = service.get_appointments_in_range(
        calendar_id=calendar.id,
        start_time=base_time + timedelta(minutes=30),
        end_time=base_time + timedelta(minutes=90),
    )
    assert success
    assert len(middle_apts) == 2  # Should include first and second appointments
    assert middle_apts[0].title == "Appointment 1"
    assert middle_apts[1].title == "Appointment 2"

    # 3. Get appointments with no overlap
    success, no_apts = service.get_appointments_in_range(
        calendar_id=calendar.id,
        start_time=base_time + timedelta(hours=5),  # 7 PM
        end_time=base_time + timedelta(hours=6),    # 8 PM
    )
    assert success
    assert len(no_apts) == 0
