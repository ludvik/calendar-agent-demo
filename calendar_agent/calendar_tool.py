from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field


class TimeSlot(BaseModel):
    start_time: datetime = Field(description="Start time of the slot")
    end_time: datetime = Field(description="End time of the slot")
    is_available: bool = Field(description="Whether the slot is available")


class CalendarTool:
    """Mock calendar tool for demonstration purposes"""
    
    def check_availability(self, time: datetime, duration: int) -> bool:
        """Mock checking if a specific time slot is available"""
        # Mock implementation: assume times between 9 AM and 5 PM are busy
        hour = time.hour
        return not (9 <= hour < 17)
    
    def find_available_slots(
        self, 
        start_time: datetime,
        end_time: datetime,
        duration: int,
        count: int = 3
    ) -> List[TimeSlot]:
        """Mock finding available time slots"""
        slots = []
        current_time = start_time
        
        while current_time < end_time and len(slots) < count:
            if self.check_availability(current_time, duration):
                slot_end = current_time + timedelta(minutes=duration)
                slots.append(
                    TimeSlot(
                        start_time=current_time,
                        end_time=slot_end,
                        is_available=True
                    )
                )
            current_time += timedelta(minutes=30)
            
        return slots
    
    def check_day_availability(self, date: datetime) -> tuple[bool, Optional[TimeSlot]]:
        """Mock checking if a day has too much free time"""
        # Mock implementation: weekends are considered free
        if date.weekday() >= 5:  # Saturday or Sunday
            return True, TimeSlot(
                start_time=datetime.combine(date.date(), datetime.min.time().replace(hour=10)),
                end_time=datetime.combine(date.date(), datetime.min.time().replace(hour=16)),
                is_available=True
            )
        return False, None
