"""Calendar service implementation using SQLite.

Note on timezone handling:
- This service internally works with UTC timezone for all datetime operations
- SQLite has limitations with timezone storage (stores datetimes without timezone info)
- The ensure_utc() function is used to normalize all datetimes to UTC
- Time display/formatting is handled at the agent layer, not in this service
- In this demo version, full cross-timezone support is limited
- For production use, consider using a database with better timezone support
"""

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Appointment, AppointmentStatus, Calendar
from .response import CalendarResponse, ResponseType


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure datetime is UTC timezone-aware.

    This function handles various edge cases:
    1. None timezone (naive datetime)
    2. Non-UTC timezone
    3. Already UTC timezone

    Args:
        dt: The datetime to convert

    Returns:
        UTC timezone-aware datetime
    """
    if dt is None:
        return None

    # If datetime is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    # If datetime has a timezone but it's not UTC, convert it
    if dt.tzinfo != timezone.utc:
        return dt.astimezone(timezone.utc)

    # Already UTC timezone-aware
    return dt


class CalendarService:
    """Service class for calendar operations."""

    def __init__(self, session_factory: sessionmaker):
        """Initialize the calendar service.

        Args:
            session_factory: SQLAlchemy session factory
        """
        self.session_factory = session_factory
        
        # Business hours are defined in local time (9 AM - 5 PM)
        # For internal calculations, these will be converted to UTC as needed
        self.business_start = time(9, 0)  # 9 AM local time
        self.business_end = time(17, 0)  # 5 PM local time
        self.min_busy_hours = 4  # Threshold for considering a day "busy"

    def create_calendar(
        self, agent_id: str, name: str, time_zone: str = "UTC"
    ) -> Calendar:
        """Create a new calendar."""
        calendar = Calendar(agent_id=agent_id, name=name, time_zone=time_zone)
        with self.session_factory() as session:
            session.add(calendar)
            session.commit()
            session.refresh(calendar)
            return calendar

    def schedule_appointment(
        self,
        calendar_id: int,
        title: str,
        start_time: datetime,
        end_time: datetime,
        status: AppointmentStatus = AppointmentStatus.TENTATIVE,
        priority: int = 3,  # Default to medium priority
        description: str = None,
        location: str = None,
    ) -> Tuple[bool, Optional[Appointment], List[Appointment]]:
        """
        Schedule a new appointment in the calendar.

        Args:
            calendar_id: ID of the calendar
            title: Title of the appointment
            start_time: Start time of the appointment
            end_time: End time of the appointment
            status: Status of the appointment (default: TENTATIVE)
            priority: Priority of the appointment (1-5, lower number = higher priority)
            description: Optional description
            location: Optional location

        Returns:
            Tuple containing:
            - Boolean indicating success
            - The created appointment if successful, None otherwise
            - List of appointments that conflict with this appointment
        """
        try:
            with self.session_factory() as session:
                # Check if calendar exists
                calendar = (
                    session.query(Calendar).filter(Calendar.id == calendar_id).first()
                )
                if not calendar:
                    return False, None, []

                # Check for conflicts with existing appointments
                conflicts = (
                    session.query(Appointment)
                    .filter(
                        Appointment.calendar_id == calendar_id,
                        Appointment.status.in_(
                            [AppointmentStatus.CONFIRMED, AppointmentStatus.TENTATIVE]
                        ),
                        Appointment.start_time < end_time,
                        Appointment.end_time > start_time,
                    )
                    .all()
                )

                # Check if there are any higher priority conflicts
                higher_priority_conflicts = [
                    c for c in conflicts if c.priority < priority
                ]
                if higher_priority_conflicts:
                    # Don't schedule if there are higher priority conflicts
                    return False, None, conflicts

                # Create new appointment
                new_appointment = Appointment(
                    calendar_id=calendar_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    status=status,
                    priority=priority,
                    description=description,
                    location=location,
                )

                # Store conflict IDs for re-querying later
                conflict_ids = [conflict.id for conflict in conflicts]

                # Add the new appointment
                session.add(new_appointment)
                session.commit()

                # Refresh to get the ID
                session.refresh(new_appointment)

                # Re-query conflicts to ensure they're attached to the session
                if conflict_ids:
                    conflicts = (
                        session.query(Appointment)
                        .filter(Appointment.id.in_(conflict_ids))
                        .all()
                    )

                return True, new_appointment, conflicts

        except Exception as e:
            print(f"Error scheduling appointment: {e}")
            return False, None, []

    def check_availability(
        self,
        calendar_id: int,
        start_time: datetime,
        end_time: datetime,
        priority: int = 5,
    ) -> bool:
        """Check if a time slot is available."""
        # Ensure times are UTC timezone-aware
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)

        with self.session_factory() as session:
            conflicts = self._find_blocking_appointments(
                session, calendar_id, start_time, end_time, priority
            )
            return not bool(conflicts)

    def find_available_slots(
        self,
        calendar_id: int,
        start_time: datetime,
        end_time: datetime,
        duration: int = 60,
        max_slots: int = 5,
        priority: int = 5,
    ) -> List[Tuple[datetime, datetime]]:
        """Find available time slots between start_time and end_time.

        Args:
            calendar_id: ID of the calendar
            start_time: Start time to search from
            end_time: End time to search until
            duration: Duration of each slot in minutes
            max_slots: Maximum number of slots to return
            priority: Priority level to consider

        Returns:
            List of (start_time, end_time) tuples
        """
        # Ensure times are UTC timezone-aware
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)

        available_slots = []
        
        # Helper function to round time to nearest 30-minute interval
        def round_to_30min(dt: datetime, round_up: bool = False) -> datetime:
            minute = dt.minute
            if round_up:
                # Round up to next 30 minutes
                rounded_minute = ((minute // 30) + (1 if minute % 30 > 0 else 0)) * 30
                if rounded_minute == 60:
                    return dt.replace(hour=dt.hour + 1, minute=0, second=0, microsecond=0)
                else:
                    return dt.replace(minute=rounded_minute, second=0, microsecond=0)
            else:
                # Round down to previous 30 minutes
                rounded_minute = (minute // 30) * 30
                return dt.replace(minute=rounded_minute, second=0, microsecond=0)
        
        # Round start_time up to next 30-minute interval
        current_time = round_to_30min(start_time, round_up=True)
        
        # Use class attributes for business hours
        
        # Helper function to check if time is within business hours
        def is_within_business_hours(dt: datetime) -> bool:
            # Convert UTC time to local time for business hours comparison
            if dt.tzinfo == timezone.utc:
                local_dt = dt.astimezone(datetime.now().astimezone().tzinfo)
            else:
                local_dt = dt
            
            t = local_dt.time()
            return self.business_start <= t < self.business_end

        while current_time + timedelta(minutes=duration) <= end_time:
            # Only consider slots that are within business hours
            if is_within_business_hours(current_time) and is_within_business_hours(current_time + timedelta(minutes=duration-1)):
                slot_end = current_time + timedelta(minutes=duration)
                if self.is_time_slot_available(
                    calendar_id, current_time, slot_end, priority
                ):
                    available_slots.append((current_time, slot_end))
                    if len(available_slots) >= max_slots:
                        break
            
            # Increment by 30 minutes for half-hour alignment
            current_time += timedelta(minutes=30)

        return available_slots

    def is_day_underutilized(
        self, calendar_id: int, date: datetime, priority: int = 5
    ) -> Tuple[bool, float]:
        """Check if a day is underutilized.

        Args:
            calendar_id: ID of the calendar
            date: Date to check
            priority: Priority level to consider

        Returns:
            Tuple of (is_underutilized, total_busy_hours)
        """
        # Ensure date is UTC timezone-aware
        date = ensure_utc(date)

        # Get start and end of day
        start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        with self.session_factory() as session:
            # Find all appointments for the day
            appointments = (
                session.query(Appointment)
                .filter(
                    and_(
                        Appointment.calendar_id == calendar_id,
                        Appointment.start_time >= start_time,
                        Appointment.end_time <= end_time,
                        Appointment.status != AppointmentStatus.CANCELLED,
                        Appointment.priority <= priority,
                    )
                )
                .all()
            )

            # Calculate total busy hours
            total_hours = sum(
                (apt.end_time - apt.start_time).total_seconds() / 3600
                for apt in appointments
            )

            # Consider a day underutilized if less than min_busy_hours
            return total_hours < self.min_busy_hours, total_hours

    def is_time_slot_available(
        self,
        calendar_id: int,
        start_time: datetime,
        end_time: datetime,
        priority: int = 5,
    ) -> bool:
        """Check if a time slot is available.

        Args:
            calendar_id: ID of the calendar
            start_time: Start time
            end_time: End time
            priority: Priority of the appointment (1-5, lower is higher priority)

        Returns:
            bool: True if the slot is available, False otherwise
        """
        with self.session_factory() as session:
            # Find any blocking appointments
            blocking = (
                session.query(Appointment)
                .filter(
                    and_(
                        Appointment.calendar_id == calendar_id,
                        # Only confirmed appointments block
                        Appointment.status == AppointmentStatus.CONFIRMED,
                        # Higher priority (lower number) can override lower priority
                        Appointment.priority <= priority,
                        # Check for overlap
                        or_(
                            and_(
                                Appointment.start_time < end_time,
                                Appointment.end_time > start_time,
                            ),
                            and_(
                                Appointment.start_time < start_time,
                                Appointment.end_time > end_time,
                            ),
                            and_(
                                Appointment.start_time > start_time,
                                Appointment.end_time < end_time,
                            ),
                        ),
                    ),
                )
                .first()
            )
            return blocking is None

    def get_appointment_type(self, appointment):
        """
        Determine the type of appointment based on its title, description, and other attributes.

        Args:
            appointment: The appointment object to categorize

        Returns:
            String representing the appointment type (internal, client_meeting, personal, administrative, other)
        """
        title = appointment.title.lower() if appointment.title else ""
        description = appointment.description.lower() if appointment.description else ""

        # Check for client meetings
        if any(
            term in title or term in description
            for term in ["client", "customer", "external", "meeting with"]
        ):
            return "client_meeting"

        # Check for internal meetings
        if any(
            term in title or term in description
            for term in ["team", "internal", "staff", "sync", "standup", "review"]
        ):
            return "internal"

        # Check for personal appointments
        if any(
            term in title or term in description
            for term in [
                "doctor",
                "dentist",
                "personal",
                "break",
                "lunch",
                "appointment",
            ]
        ):
            return "personal"

        # Check for administrative tasks
        if any(
            term in title or term in description
            for term in ["admin", "paperwork", "report", "planning", "email"]
        ):
            return "administrative"

        # Default type
        return "other"

    def _find_blocking_appointments(
        self,
        session: Session,
        calendar_id: int,
        start_time: datetime,
        end_time: datetime,
        priority: int,
    ) -> List[Appointment]:
        """Find appointments that would block a time slot."""
        return (
            session.query(Appointment)
            .filter(
                and_(
                    Appointment.calendar_id == calendar_id,
                    Appointment.status != AppointmentStatus.CANCELLED,
                    Appointment.priority <= priority,
                    # Check for overlap
                    or_(
                        and_(
                            Appointment.start_time < end_time,
                            Appointment.end_time > start_time,
                        ),
                        and_(
                            Appointment.start_time < start_time,
                            Appointment.end_time > end_time,
                        ),
                        and_(
                            Appointment.start_time > start_time,
                            Appointment.end_time < end_time,
                        ),
                    ),
                )
            )
            .all()
        )

    def cancel_appointment(self, calendar_id: int, appointment_id: int) -> bool:
        """Cancel an appointment by setting its status to CANCELLED.

        Args:
            calendar_id: ID of the calendar
            appointment_id: ID of the appointment to cancel

        Returns:
            bool: True if successfully cancelled, False otherwise
        """
        with self.session_factory() as session:
            appointment = (
                session.query(Appointment).filter_by(id=appointment_id).first()
            )
            if not appointment:
                return False

            appointment.status = AppointmentStatus.CANCELLED
            appointment.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True

    def update_appointment(
        self,
        calendar_id: int,
        appointment_id: int,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[AppointmentStatus] = None,
        priority: Optional[int] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Tuple[bool, Optional[Appointment], List[Appointment]]:
        """
        Update an existing appointment.

        Args:
            calendar_id: ID of the calendar
            appointment_id: ID of the appointment to update
            title: New title (optional)
            start_time: New start time (optional)
            end_time: New end time (optional)
            status: New status (optional)
            priority: New priority (optional)
            description: New description (optional)
            location: New location (optional)

        Returns:
            Tuple of (success, updated_appointment, conflicting_appointments)
        """
        try:
            with self.session_factory() as session:
                # Find the appointment
                appointment = (
                    session.query(Appointment).filter_by(id=appointment_id).first()
                )
                if not appointment:
                    return False, None, []

                # Store original values for conflict checking
                original_start = appointment.start_time
                original_end = appointment.end_time

                # Update fields if provided
                if title is not None:
                    appointment.title = title
                if start_time is not None:
                    appointment.start_time = ensure_utc(start_time)
                if end_time is not None:
                    appointment.end_time = ensure_utc(end_time)
                if status is not None:
                    appointment.status = status
                if priority is not None:
                    appointment.priority = priority
                if description is not None:
                    appointment.description = description
                if location is not None:
                    appointment.location = location

                # Update the updated_at timestamp
                appointment.updated_at = datetime.now(timezone.utc)

                # Check for conflicts if time has changed
                conflicts = []
                if (
                    start_time is not None or end_time is not None
                ) and appointment.status != AppointmentStatus.CANCELLED:
                    new_start = appointment.start_time
                    new_end = appointment.end_time

                    # Find conflicting appointments
                    conflicts = self._find_blocking_appointments(
                        session, calendar_id, new_start, new_end, appointment.priority
                    )

                    # Remove self from conflicts
                    conflicts = [c for c in conflicts if c.id != appointment_id]

                # Commit changes
                session.commit()

                # Create a fresh copy of the appointment to return
                updated_appointment = (
                    session.query(Appointment).filter_by(id=appointment_id).first()
                )

                return True, updated_appointment, conflicts
        except Exception as e:
            print(f"Error in CalendarService.update_appointment: {e}")
            return False, None, []

    def get_appointments_in_range(
        self,
        calendar_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> Tuple[bool, List[Appointment]]:
        """Get all appointments within a time range.

        Args:
            calendar_id: ID of the calendar
            start_time: Start of the range
            end_time: End of the range

        Returns:
            Tuple of (success, appointments)
        """
        try:
            with self.session_factory() as session:
                appointments = (
                    session.query(Appointment)
                    .filter(
                        Appointment.calendar_id == calendar_id,
                        Appointment.status == AppointmentStatus.CONFIRMED,
                        Appointment.start_time < end_time,
                        Appointment.end_time > start_time,
                    )
                    .order_by(Appointment.start_time)
                    .all()
                )
                return True, appointments
        except Exception:
            return False, []
