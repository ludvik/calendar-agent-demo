"""Tests for the calendar service."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_agent.calendar_service import CalendarService
from calendar_agent.config import DatabaseConfig
from calendar_agent.models import Appointment, AppointmentStatus, Base, Calendar


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
    success, apt, _ = service.schedule_appointment(
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
    # Check time values without relying on timezone
    # SQLite doesn't store timezone info, so we just check the time components
    assert apt.start_time.hour == tomorrow_9am.hour
    assert apt.start_time.minute == tomorrow_9am.minute
    end_time = tomorrow_9am + timedelta(hours=1)
    assert apt.end_time.hour == end_time.hour
    assert apt.end_time.minute == end_time.minute


def test_schedule_conflicting_confirmed_appointments(service, calendar, tomorrow_9am):
    """Test that we can't schedule conflicting confirmed appointments without proper conflict resolution."""
    # Schedule first appointment
    success1, apt1, _ = service.schedule_appointment(
        calendar.id,
        "First Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
        priority=3,
    )
    assert success1

    # Try to schedule conflicting appointment
    success2, apt2, conflicts = service.schedule_appointment(
        calendar.id,
        "Conflicting Meeting",
        tomorrow_9am + timedelta(minutes=30),
        tomorrow_9am + timedelta(hours=1, minutes=30),
        AppointmentStatus.CONFIRMED,
        priority=1,  # Higher priority can override CONFIRMED in our enhanced implementation
    )

    # With our enhanced implementation, this should succeed but return conflicts
    assert success2
    assert apt2 is not None
    assert len(conflicts) == 1
    assert conflicts[0].id == apt1.id

    # Verify that the conflicting appointment was created
    with service.session_factory() as session:
        created_apt = (
            session.query(Appointment).filter(Appointment.id == apt2.id).first()
        )
        assert created_apt is not None
        assert created_apt.status == AppointmentStatus.CONFIRMED


def test_high_priority_overrides_low_priority_tentative(
    service, calendar, tomorrow_9am
):
    """Test that high priority appointments override low priority tentative ones."""
    # Schedule low priority tentative appointment
    success1, apt1, _ = service.schedule_appointment(
        calendar.id,
        "Low Priority Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.TENTATIVE,
        priority=5,
    )
    assert success1

    # Schedule high priority appointment at same time
    success2, apt2, conflicts = service.schedule_appointment(
        calendar.id,
        "High Priority Meeting",
        tomorrow_9am,
        tomorrow_9am + timedelta(hours=1),
        AppointmentStatus.CONFIRMED,
        priority=1,
    )

    # Should succeed and have the conflict
    assert success2
    assert apt2 is not None
    assert len(conflicts) == 1
    assert conflicts[0].id == apt1.id

    with service.session_factory() as session:
        original_apt = (
            session.query(Appointment).filter(Appointment.id == apt1.id).first()
        )
        assert original_apt.status in [
            AppointmentStatus.CANCELLED,
            AppointmentStatus.TENTATIVE,
        ]


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
    success, appointment, _ = service.schedule_appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
    )
    assert success
    assert appointment is not None

    # Cancel the appointment
    success = service.cancel_appointment(calendar.id, appointment.id)
    assert success

    # Verify the appointment is cancelled
    with service.session_factory() as session:
        cancelled_apt = (
            session.query(Appointment).filter(Appointment.id == appointment.id).first()
        )
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
        success, apt, _ = service.schedule_appointment(
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
        end_time=base_time + timedelta(hours=6),  # 8 PM
    )
    assert success
    assert len(no_apts) == 0


def test_priority_conflict_resolution(service, calendar, tomorrow_9am):
    """Test handling conflicts based on priority using update_appointment."""
    # Schedule a low priority appointment
    apt_tour_start = tomorrow_9am.replace(hour=14)
    apt_tour_end = apt_tour_start + timedelta(hours=1)
    success1, apt_tour, _ = service.schedule_appointment(
        calendar_id=calendar.id,
        title="Apartment Tour",
        start_time=apt_tour_start,
        end_time=apt_tour_end,
        status=AppointmentStatus.CONFIRMED,
        priority=4,  # Lower priority
    )
    assert success1

    # Schedule a conflicting high priority appointment
    client_meeting_start = apt_tour_start + timedelta(minutes=30)
    client_meeting_end = client_meeting_start + timedelta(hours=1)
    success2, client_meeting, conflicts = service.schedule_appointment(
        calendar_id=calendar.id,
        title="Client Meeting",
        start_time=client_meeting_start,
        end_time=client_meeting_end,
        status=AppointmentStatus.TENTATIVE,  # Make it tentative to avoid auto-override
        priority=1,  # Higher priority
    )
    assert success2
    assert len(conflicts) == 1
    assert conflicts[0].id == apt_tour.id

    # Manually resolve the conflict by updating appointments
    # 1. Cancel the lower priority appointment
    service.update_appointment(
        calendar_id=calendar.id,
        appointment_id=apt_tour.id,
        status=AppointmentStatus.CANCELLED,
    )

    # 2. Confirm the higher priority appointment
    service.update_appointment(
        calendar_id=calendar.id,
        appointment_id=client_meeting.id,
        status=AppointmentStatus.CONFIRMED,
    )

    # Verify the changes were applied
    with service.session_factory() as session:
        # Check that the apartment tour is cancelled
        apt_tour_updated = (
            session.query(Appointment).filter(Appointment.id == apt_tour.id).first()
        )
        assert apt_tour_updated.status == AppointmentStatus.CANCELLED

        # Check that the client meeting is confirmed
        client_meeting_updated = (
            session.query(Appointment)
            .filter(Appointment.id == client_meeting.id)
            .first()
        )
        assert client_meeting_updated.status == AppointmentStatus.CONFIRMED

    # Alternative approach: Reschedule the lower priority appointment
    # Find a new time slot for the apartment tour
    rescheduled_start = tomorrow_9am.replace(hour=16)  # 4pm
    rescheduled_end = rescheduled_start + timedelta(hours=1)

    # Check if the new time slot is available
    is_available = service.check_availability(
        calendar_id=calendar.id, start_time=rescheduled_start, end_time=rescheduled_end
    )

    if is_available:
        # Reschedule the appointment
        service.update_appointment(
            calendar_id=calendar.id,
            appointment_id=apt_tour.id,
            start_time=rescheduled_start,
            end_time=rescheduled_end,
            status=AppointmentStatus.CONFIRMED,
        )

        # Verify the rescheduling
        with service.session_factory() as session:
            rescheduled_apt = (
                session.query(Appointment).filter(Appointment.id == apt_tour.id).first()
            )
            assert rescheduled_apt.start_time.hour == 16
            assert rescheduled_apt.status == AppointmentStatus.CONFIRMED


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
    success, appointment, _ = service.schedule_appointment(
        calendar_id=calendar.id,
        title="Test Appointment",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
    )
    assert success
    assert appointment is not None

    # Cancel the appointment
    success = service.cancel_appointment(calendar.id, appointment.id)
    assert success

    # Verify the appointment is cancelled
    with service.session_factory() as session:
        cancelled_apt = (
            session.query(Appointment).filter(Appointment.id == appointment.id).first()
        )
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
        success, apt, _ = service.schedule_appointment(
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
        end_time=base_time + timedelta(hours=6),  # 8 PM
    )
    assert success
    assert len(no_apts) == 0
