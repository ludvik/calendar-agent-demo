from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import List, Optional, Tuple, Dict

from pydantic import BaseModel, Field

from .calendar_service import CalendarService
from .models import AppointmentStatus
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
        self.active_calendar_id = None

        # Standard business hours
        self.business_start = time(9, 0)
        self.business_end = time(17, 0)

    def set_active_calendar(self, calendar_id: int) -> None:
        """Set the active calendar ID."""
        self.active_calendar_id = calendar_id

    def is_within_business_hours(self, dt: datetime) -> bool:
        """Check if a datetime is within business hours"""
        t = dt.time()
        return self.business_start <= t < self.business_end

    def is_busy_time(self, dt: datetime, duration: int = 60) -> bool:
        """Check if a datetime is busy.

        Args:
            dt: The datetime to check
            duration: Duration in minutes
        """
        if not self.active_calendar_id:
            raise ValueError("No active calendar set")

        end_time = dt + timedelta(minutes=duration)
        return not self.calendar_service.is_time_slot_available(
            self.active_calendar_id, dt, end_time
        )

    def find_available_slots(
        self,
        start_time: datetime,
        end_time: datetime,
        duration: int = 60,
        count: int = 3,
    ) -> List[TimeSlot]:
        """Find available time slots in a given range.

        Args:
            start_time: Start of the range to search
            end_time: End of the range to search
            duration: Desired duration in minutes
            count: Maximum number of slots to return
        """
        if not self.active_calendar_id:
            raise ValueError("No active calendar set")

        current = start_time
        slots = []

        while current + timedelta(minutes=duration) <= end_time and len(slots) < count:
            if self.is_within_business_hours(current):
                is_available = self.calendar_service.is_time_slot_available(
                    self.active_calendar_id,
                    current,
                    current + timedelta(minutes=duration),
                )
                if is_available:
                    slots.append(
                        TimeSlot(
                            start_time=current,
                            end_time=current + timedelta(minutes=duration),
                            is_available=True,
                        )
                    )
            current += timedelta(minutes=30)  # Try every 30 minutes

        return slots

    def schedule_appointment(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        status: AppointmentStatus = AppointmentStatus.CONFIRMED,
        priority: int = 3,
        description: str = None,
        location: str = None,
    ) -> Tuple[bool, Optional[Dict], List[Dict]]:
        """
        Schedule a new appointment.
        
        Args:
            title: Title of the appointment
            start_time: Start time
            end_time: End time
            status: Status of the appointment
            priority: Priority of the appointment (1-5, lower is higher priority)
            description: Optional description
            location: Optional location
            
        Returns:
            Tuple of (success, appointment_dict, conflicting_appointments)
        """
        try:
            success, appointment, conflicts = self.calendar_service.schedule_appointment(
                calendar_id=self.active_calendar_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                status=status,
                priority=priority,
                description=description,
                location=location,
            )
            
            if success and appointment:
                # Convert to dict for the agent
                appointment_dict = {
                    "id": appointment.id,
                    "title": appointment.title,
                    "start_time": appointment.start_time.isoformat(),
                    "end_time": appointment.end_time.isoformat(),
                    "status": appointment.status.value,
                    "priority": appointment.priority,
                }
                
                # Convert conflicting appointments to dict
                conflicts_dict = []
                for appt in conflicts:
                    conflicts_dict.append({
                        "id": appt.id,
                        "title": appt.title,
                        "start_time": appt.start_time.isoformat(),
                        "end_time": appt.end_time.isoformat(),
                        "status": appt.status.value,
                        "priority": appt.priority,
                    })
                
                return success, appointment_dict, conflicts_dict
            return success, None, []
        except Exception as e:
            print(f"Error in CalendarTool.schedule_appointment: {e}")
            return False, None, []

    def resolve_conflicts(
        self,
        for_appointment_id: int,
        strategies: Dict
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Resolve conflicts for a previously scheduled appointment.
        
        Args:
            for_appointment_id: ID of the appointment to resolve conflicts for
            strategies: Dictionary of conflict resolution strategies
                Example:
                {
                    "by_type": {
                        "internal": {
                            "action": "reschedule", 
                            "target_window": "2025-03-02T09:00-12:00",
                            "preferred_hours": [9, 10, 14, 15],
                            "avoid_lunch_hour": true
                        },
                        "client_meeting": {
                            "action": "reschedule", 
                            "target_window": "2025-03-01T17:00-19:00"
                        }
                    },
                    "by_priority": true,
                    "fallback": {
                        "action": "reschedule",
                        "window_days": 7,
                        "preferred_hours": [9, 10, 11, 14, 15, 16]
                    }
                }
                
        Returns:
            Tuple of (resolved_appointments, unresolved_appointments)
        """
        try:
            resolved, unresolved = self.calendar_service.resolve_conflicts(
                for_appointment_id=for_appointment_id,
                strategies=strategies
            )
            
            # Convert resolved appointments to dict
            resolved_dict = []
            for appt in resolved:
                # Determine what action was taken
                action = "rescheduled"
                if appt.status == AppointmentStatus.CANCELLED:
                    action = "cancelled"
                
                resolved_dict.append({
                    "id": appt.id,
                    "title": appt.title,
                    "start_time": appt.start_time.isoformat(),
                    "end_time": appt.end_time.isoformat(),
                    "status": appt.status.value,
                    "priority": appt.priority,
                    "action": action,
                    "type": self.get_appointment_type(appt)
                })
                
            # Convert unresolved appointments to dict
            unresolved_dict = []
            for appt in unresolved:
                unresolved_dict.append({
                    "id": appt.id,
                    "title": appt.title,
                    "start_time": appt.start_time.isoformat(),
                    "end_time": appt.end_time.isoformat(),
                    "status": appt.status.value,
                    "priority": appt.priority,
                    "reason": "Cannot find suitable time or override equal/higher priority",
                    "type": self.get_appointment_type(appt)
                })
                
            return resolved_dict, unresolved_dict
        except Exception as e:
            print(f"Error in CalendarTool.resolve_conflicts: {e}")
            return [], []

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

    def cancel_appointment(self, appointment_id: int) -> bool:
        """Cancel an appointment.

        Args:
            appointment_id: ID of the appointment to cancel
        """
        if not self.active_calendar_id:
            raise ValueError("No active calendar set")

        return self.calendar_service.cancel_appointment(appointment_id)

    def check_availability(
        self, start_time: datetime, end_time: datetime, priority: int = 5
    ) -> bool:
        """Check if a time slot is available."""
        if not self.active_calendar_id:
            raise ValueError("No active calendar set")
        return self.calendar_service.check_availability(
            self.active_calendar_id, start_time, end_time, priority
        )

    def check_day_availability(self, date: datetime) -> CalendarResponse:
        """Check availability for a given day.

        Args:
            date: The date to check

        Returns:
            CalendarResponse with availability information
        """
        if not self.active_calendar_id:
            return CalendarResponse(
                type=ResponseType.CALENDAR,
                message="No active calendar selected.",
                action_taken="Failed: No active calendar",
                suggested_slots=None,
            )

        # Get all appointments for the day
        start_time = datetime.combine(date.date(), self.business_start)
        end_time = datetime.combine(date.date(), self.business_end)
        success, appointments = self.calendar_service.get_appointments_in_range(
            calendar_id=self.active_calendar_id,
            start_time=start_time,
            end_time=end_time,
        )

        if not success:
            return CalendarResponse(
                type=ResponseType.CALENDAR,
                message="Failed to retrieve appointments.",
                action_taken="Failed: Could not get appointments",
                suggested_slots=None,
            )

        # Build list of busy slots
        busy_slots = []
        for appt in appointments:
            busy_slots.append(
                {"start": appt.start_time, "end": appt.end_time, "title": appt.title}
            )

        # Format message
        if not busy_slots:
            message = f"The entire day from {self.business_start} to {self.business_end} is available."
            action_taken = "Found: Day is completely free"
        else:
            busy_times = [
                f"{slot['start'].strftime('%I:%M %p')} - {slot['end'].strftime('%I:%M %p')}: {slot['title']}"
                for slot in busy_slots
            ]
            message = f"Busy times:\n" + "\n".join(busy_times)
            action_taken = f"Found {len(busy_slots)} appointments"

        return CalendarResponse(
            type=ResponseType.CALENDAR,
            message=message,
            action_taken=action_taken,
            suggested_slots=None,
        )
