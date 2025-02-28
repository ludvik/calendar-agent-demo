from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from .calendar_service import CalendarService
from .models import Appointment, AppointmentStatus
from .response import CalendarResponse, ResponseType, TimeSlot


class TimeSlot(BaseModel):
    start_time: datetime = Field(description="Start time of the slot")
    end_time: datetime = Field(description="End time of the slot")
    is_available: bool = Field(description="Whether the slot is available")


class CalendarTool:
    """Tool for interacting with calendar service"""

    def __init__(self, calendar_service: CalendarService):
        """Initialize with calendar service.

        Args:
            calendar_service: The calendar service to use
        """
        self.calendar_service = calendar_service

        # Standard business hours
        self.business_start = time(9, 0)
        self.business_end = time(17, 0)

    def is_within_business_hours(self, dt: datetime) -> bool:
        """Check if a datetime is within business hours"""
        t = dt.time()
        return self.business_start <= t < self.business_end

    def is_busy_time(self, calendar_id: int, dt: datetime, duration: int = 60) -> bool:
        """Check if a datetime is busy.

        Args:
            calendar_id: ID of the calendar to check
            dt: The datetime to check
            duration: Duration in minutes
        """
        end_time = dt + timedelta(minutes=duration)
        return not self.calendar_service.is_time_slot_available(
            calendar_id, dt, end_time
        )

    # def find_available_slots(
    #     self,
    #     calendar_id: int,
    #     start_time: datetime,
    #     end_time: datetime,
    #     duration: int = 60,
    #     count: int = 3,
    # ) -> List[TimeSlot]:
    #     """Find available time slots in a given range.
    #
    #     Args:
    #         calendar_id: ID of the calendar to check
    #         start_time: Start of the range to search
    #         end_time: End of the range to search
    #         duration: Desired duration in minutes
    #         count: Maximum number of slots to return
    #     """
    #     current = start_time
    #     slots = []
    #
    #     while current + timedelta(minutes=duration) <= end_time and len(slots) < count:
    #         if self.is_within_business_hours(current):
    #             is_available = self.calendar_service.is_time_slot_available(
    #                 calendar_id,
    #                 current,
    #                 current + timedelta(minutes=duration),
    #             )
    #             if is_available:
    #                 slots.append(
    #                     TimeSlot(
    #                         start_time=current,
    #                         end_time=current + timedelta(minutes=duration),
    #                         is_available=True,
    #                     )
    #                 )
    #         current += timedelta(minutes=30)  # Try every 30 minutes
    #
    #     return slots

    # def schedule_appointment(
    #     self,
    #     calendar_id: int,
    #     title: str,
    #     start_time: datetime,
    #     end_time: datetime,
    #     status: AppointmentStatus = AppointmentStatus.CONFIRMED,
    #     priority: int = 3,
    #     description: str = None,
    #     location: str = None,
    # ) -> Tuple[bool, Optional[Dict], List[Dict]]:
    #     """
    #     Schedule a new appointment.

    #     Args:
    #         calendar_id: ID of the calendar to schedule in
    #         title: Title of the appointment
    #         start_time: Start time
    #         end_time: End time
    #         status: Status of the appointment
    #         priority: Priority of the appointment (1-5, lower is higher priority)
    #         description: Optional description
    #         location: Optional location

    #     Returns:
    #         Tuple of (success, appointment_dict, conflicting_appointments)
    #     """
    #     try:
    #         success, appointment, conflicts = (
    #             self.calendar_service.schedule_appointment(
    #                 calendar_id=calendar_id,
    #                 title=title,
    #                 start_time=start_time,
    #                 end_time=end_time,
    #                 status=status,
    #                 priority=priority,
    #                 description=description,
    #                 location=location,
    #             )
    #         )

    #         if success and appointment:
    #             # Convert to dict for the agent
    #             appointment_dict = {
    #                 "id": appointment.id,
    #                 "title": appointment.title,
    #                 "start_time": appointment.start_time.isoformat(),
    #                 "end_time": appointment.end_time.isoformat(),
    #                 "status": appointment.status.value,
    #                 "priority": appointment.priority,
    #                 "description": appointment.description,
    #                 "location": appointment.location,
    #                 "type": self.get_appointment_type(appointment),
    #             }

    #             # Convert conflicting appointments to dict
    #             conflicts_dict = []
    #             for appt in conflicts:
    #                 conflicts_dict.append(
    #                     {
    #                         "id": appt.id,
    #                         "title": appt.title,
    #                         "start_time": appt.start_time.isoformat(),
    #                         "end_time": appt.end_time.isoformat(),
    #                         "status": appt.status.value,
    #                         "priority": appt.priority,
    #                         "description": appt.description,
    #                         "location": appt.location,
    #                         "type": self.get_appointment_type(appt),
    #                     }
    #                 )

    #             return success, appointment_dict, conflicts_dict
    #         return success, None, []
    #     except Exception as e:
    #         print(f"Error in CalendarTool.schedule_appointment: {e}")
    #         return False, None, []

    def get_appointment_type(self, appointment):
        """
        Determine the type of appointment based on its title, description, and other attributes.

        Args:
            appointment: The appointment object to categorize

        Returns:
            String representing the appointment type (internal, client_meeting, personal, administrative, other)
        """
        # Use the calendar service's method to determine the appointment type
        return self.calendar_service.get_appointment_type(appointment)

    def get_appointments(
        self,
        calendar_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        title_filter: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get appointments within a time range with optional filters.

        Args:
            calendar_id: ID of the calendar to retrieve appointments from
            start_time: Start of the time range (optional)
            end_time: End of the time range (optional)
            title_filter: Filter appointments by title (optional)
            priority: Filter appointments by priority (optional)

        Returns:
            List of appointment dictionaries
        """
        try:
            # Get appointments in range
            success, appointments = self.calendar_service.get_appointments_in_range(
                start_time=start_time
                or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                end_time=end_time or (datetime.now() + timedelta(days=7)),
                calendar_id=calendar_id,
            )

            if not success or not appointments:
                return []

            # Apply filters
            filtered_appointments = []
            for appointment in appointments:
                # Skip cancelled appointments
                if appointment.status == AppointmentStatus.CANCELLED:
                    continue

                # Apply title filter if specified
                if (
                    title_filter
                    and title_filter.lower() not in appointment.title.lower()
                ):
                    continue

                # Apply priority filter if specified
                if priority is not None and appointment.priority != priority:
                    continue

                # Convert to dictionary
                appointment_dict = {
                    "id": appointment.id,
                    "title": appointment.title,
                    "start_time": appointment.start_time.isoformat(),
                    "end_time": appointment.end_time.isoformat(),
                    "status": appointment.status.value,
                    "priority": appointment.priority,
                    "description": appointment.description,
                    "location": appointment.location,
                    "type": self.get_appointment_type(appointment),
                }

                filtered_appointments.append(appointment_dict)

            return filtered_appointments
        except Exception as e:
            print(f"Error in CalendarTool.get_appointments: {e}")
            return []

    def get_appointment(self, calendar_id: int, appointment_id: int) -> dict:
        """
        Get a specific appointment by ID.

        Args:
            calendar_id: ID of the calendar to retrieve from
            appointment_id: ID of the appointment to retrieve

        Returns:
            Dictionary with appointment details or None if not found
        """
        try:
            with self.calendar_service.session_factory() as session:
                appointment = (
                    session.query(Appointment)
                    .filter(Appointment.id == appointment_id)
                    .first()
                )

                if not appointment:
                    return None

                return {
                    "id": appointment.id,
                    "title": appointment.title,
                    "start_time": appointment.start_time,
                    "end_time": appointment.end_time,
                    "status": appointment.status.value,
                    "priority": appointment.priority,
                    "description": appointment.description,
                    "location": appointment.location,
                }
        except Exception as e:
            print(f"Error in CalendarTool.get_appointment: {e}")
            return None

    def cancel_appointment(self, calendar_id: int, appointment_id: int) -> bool:
        """Cancel an appointment.

        Args:
            calendar_id: ID of the calendar to cancel from
            appointment_id: ID of the appointment to cancel
        """
        return self.calendar_service.cancel_appointment(calendar_id, appointment_id)

    # def update_appointment(
    #     self,
    #     calendar_id: int,
    #     appointment_id: int,
    #     title: Optional[str] = None,
    #     start_time: Optional[datetime] = None,
    #     end_time: Optional[datetime] = None,
    #     status: Optional[AppointmentStatus] = None,
    #     priority: Optional[int] = None,
    #     description: Optional[str] = None,
    #     location: Optional[str] = None,
    # ) -> Tuple[bool, Optional[dict], List[dict]]:
    #     """
    #     Update an existing appointment.

    #     Args:
    #         calendar_id: ID of the calendar to update in
    #         appointment_id: ID of the appointment to update
    #         title: New title (optional)
    #         start_time: New start time (optional)
    #         end_time: New end time (optional)
    #         status: New status (optional)
    #         priority: New priority (optional)
    #         description: New description (optional)
    #         location: New location (optional)

    #     Returns:
    #         Tuple of (success, updated_appointment_dict, conflicting_appointments_dicts)
    #     """
    #     try:
    #         # Call the calendar service's update_appointment method
    #         success, updated_appointment, conflicts = (
    #             self.calendar_service.update_appointment(
    #                 calendar_id=calendar_id,
    #                 appointment_id=appointment_id,
    #                 title=title,
    #                 start_time=start_time,
    #                 end_time=end_time,
    #                 status=status,
    #                 priority=priority,
    #                 description=description,
    #                 location=location,
    #             )
    #         )

    #         if not success or not updated_appointment:
    #             return False, None, []

    #         # Immediately convert appointment to dictionary to avoid detached object issues
    #         try:
    #             updated_dict = {
    #                 "id": updated_appointment.id,
    #                 "title": updated_appointment.title,
    #                 "start_time": (
    #                     updated_appointment.start_time.isoformat()
    #                     if updated_appointment.start_time
    #                     else None
    #                 ),
    #                 "end_time": (
    #                     updated_appointment.end_time.isoformat()
    #                     if updated_appointment.end_time
    #                     else None
    #                 ),
    #                 "status": (
    #                     updated_appointment.status.value
    #                     if updated_appointment.status
    #                     else None
    #                 ),
    #                 "priority": updated_appointment.priority,
    #                 "description": updated_appointment.description,
    #                 "location": updated_appointment.location,
    #                 "type": self.get_appointment_type(updated_appointment),
    #             }
    #         except Exception as e:
    #             print(f"Error converting updated appointment to dict: {e}")
    #             return False, None, []

    #         # Immediately convert conflicts to dictionaries to avoid detached object issues
    #         conflict_dicts = []
    #         try:
    #             for conflict in conflicts:
    #                 conflict_dict = {
    #                     "id": conflict.id,
    #                     "title": conflict.title,
    #                     "start_time": (
    #                         conflict.start_time.isoformat()
    #                         if conflict.start_time
    #                         else None
    #                     ),
    #                     "end_time": (
    #                         conflict.end_time.isoformat() if conflict.end_time else None
    #                     ),
    #                     "status": conflict.status.value if conflict.status else None,
    #                     "priority": conflict.priority,
    #                     "description": conflict.description,
    #                     "location": conflict.location,
    #                     "type": self.get_appointment_type(conflict),
    #                 }
    #                 conflict_dicts.append(conflict_dict)
    #         except Exception as e:
    #             print(f"Error converting conflict to dict: {e}")
    #             # Continue with what we have

    #         return success, updated_dict, conflict_dicts
    #     except Exception as e:
    #         print(f"Error in CalendarTool.update_appointment: {e}")
    #         return False, None, []

    # def check_day_availability(
    #     self, calendar_id: int, date: datetime
    # ) -> CalendarResponse:
    #     """Check availability for a given day.
    #
    #     Args:
    #         calendar_id: ID of the calendar to check
    #         date: The date to check
    #
    #     Returns:
    #         CalendarResponse with availability information
    #     """
    #     # Get all appointments for the day
    #     start_time = datetime.combine(date.date(), self.business_start)
    #     end_time = datetime.combine(date.date(), self.business_end)
    #     success, appointments = self.calendar_service.get_appointments_in_range(
    #         start_time=start_time,
    #         end_time=end_time,
    #         calendar_id=calendar_id,
    #     )
    #
    #     if not success:
    #         return CalendarResponse(
    #             type="CALENDAR",
    #             message="Failed to retrieve appointments.",
    #             action_taken="Failed: Could not get appointments",
    #             suggested_slots=None,
    #         )
    #
    #     # Build list of busy slots
    #     busy_slots = []
    #     for appt in appointments:
    #         busy_slots.append(
    #             {"start": appt.start_time, "end": appt.end_time, "title": appt.title}
    #         )
    #
    #     # Format message
    #     if not busy_slots:
    #         message = f"The entire day from {self.business_start} to {self.business_end} is available."
    #         action_taken = "Found: Day is completely free"
    #     else:
    #         busy_times = [
    #             f"{slot['start'].strftime('%I:%M %p')} - {slot['end'].strftime('%I:%M %p')}: {slot['title']}"
    #             for slot in busy_slots
    #         ]
    #         message = f"Busy times:\n" + "\n".join(busy_times)
    #         action_taken = f"Found {len(busy_slots)} appointments"
    #
    #     return CalendarResponse(
    #         type="CALENDAR",
    #         message=message,
    #         action_taken=action_taken,
    #         suggested_slots=None,
    #     )
