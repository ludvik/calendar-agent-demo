"""Response types for calendar agent."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ResponseType(str, Enum):
    """Type of response from calendar agent."""

    BASE = "base"
    CALENDAR = "calendar"


class BaseResponse(BaseModel):
    """Base response from calendar agent."""

    type: ResponseType = ResponseType.BASE
    message: str


class TimeSlot(BaseModel):
    """Time slot for calendar."""

    start_time: str
    end_time: str
    duration: int


class CalendarResponse(BaseResponse):
    """Calendar-specific response from agent."""

    type: ResponseType = ResponseType.CALENDAR
    action_taken: str
    suggested_slots: Optional[List[TimeSlot]] = None
