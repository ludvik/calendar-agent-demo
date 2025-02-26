"""Calendar service implementation using SQLite."""

from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Appointment, AppointmentStatus, Calendar
from .response import CalendarResponse, ResponseType


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC timezone-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class CalendarService:
    """Service class for calendar operations."""

    def __init__(self, session_factory: sessionmaker):
        """Initialize the calendar service.

        Args:
            session_factory: SQLAlchemy session factory
        """
        self.session_factory = session_factory
        self.business_start = time(9, 0)  # 9 AM
        self.business_end = time(17, 0)  # 5 PM
        self.min_busy_hours = 4  # Threshold for considering a day "busy"
        self.active_calendar_id = None

    def set_active_calendar(self, calendar_id: int):
        """Set the active calendar ID."""
        self.active_calendar_id = calendar_id

    def create_calendar(
        self, agent_id: str, name: str, time_zone: str = "UTC"
    ) -> Calendar:
        """Create a new calendar."""
        calendar = Calendar(agent_id=agent_id, name=name, time_zone=time_zone)
        with self.session_factory() as session:
            session.add(calendar)
            session.commit()
            # Get the calendar ID
            calendar_id = calendar.id

        # Return a fresh instance from a new session
        with self.session_factory() as session:
            return session.get(Calendar, calendar_id)

    def schedule_appointment(
        self,
        calendar_id: int,
        title: str,
        start_time: datetime,
        end_time: datetime,
        status: AppointmentStatus = AppointmentStatus.TENTATIVE,
        priority: int = 5,
    ) -> Tuple[bool, Appointment]:
        """Schedule a new appointment.

        Args:
            calendar_id: ID of the calendar
            title: Title of the appointment
            start_time: Start time
            end_time: End time
            status: Status of the appointment
            priority: Priority of the appointment (1-5, lower is higher priority)

        Returns:
            Tuple of (success, appointment)
        """
        # Ensure times are UTC timezone-aware
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)

        with self.session_factory() as session:
            # Find any conflicting appointments
            conflicts = (
                session.query(Appointment)
                .filter(
                    and_(
                        Appointment.calendar_id == calendar_id,
                        Appointment.status != AppointmentStatus.CANCELLED,
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
                .all()
            )

            # Check if any confirmed appointments block this
            for conflict in conflicts:
                if conflict.status == AppointmentStatus.CONFIRMED:
                    return False, None

            # If we're scheduling a confirmed appointment, cancel any tentative ones
            if status == AppointmentStatus.CONFIRMED:
                for conflict in conflicts:
                    if conflict.status == AppointmentStatus.TENTATIVE:
                        conflict.status = AppointmentStatus.CANCELLED

            # Create the appointment
            appointment = Appointment(
                calendar_id=calendar_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                status=status,
                priority=priority,
            )
            session.add(appointment)
            session.commit()
            session.refresh(appointment)
            return True, appointment

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
        current_time = start_time

        while current_time + timedelta(minutes=duration) <= end_time:
            slot_end = current_time + timedelta(minutes=duration)
            if self.is_time_slot_available(
                calendar_id, current_time, slot_end, priority
            ):
                available_slots.append((current_time, slot_end))
                if len(available_slots) >= max_slots:
                    break
            current_time += timedelta(minutes=duration)

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

    def cancel_appointment(self, appointment_id: int) -> bool:
        """Cancel an appointment by setting its status to CANCELLED.

        Args:
            appointment_id: ID of the appointment to cancel

        Returns:
            bool: True if successfully cancelled, False otherwise
        """
        try:
            with self.session_factory() as session:
                appointment = (
                    session.query(Appointment)
                    .filter(Appointment.id == appointment_id)
                    .first()
                )

                if not appointment:
                    return False

                appointment.status = AppointmentStatus.CANCELLED
                session.commit()
                return True
        except SQLAlchemyError:
            return False

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
        except SQLAlchemyError:
            return False, []
