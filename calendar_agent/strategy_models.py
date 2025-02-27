"""
Pydantic models for calendar conflict resolution strategies.
"""

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class RescheduleStrategy(BaseModel):
    """Strategy for rescheduling an appointment."""

    action: Literal["reschedule"] = "reschedule"
    target_window: Optional[str] = Field(
        None,
        description="Time window in format 'YYYY-MM-DDThh:mm-hh:mm' (e.g., '2025-03-02T09:00-12:00')",
    )
    window_days: Optional[int] = Field(
        None, description="Number of days to look ahead for available slots"
    )
    preferred_hours: Optional[List[int]] = Field(
        None, description="List of preferred hours (9-17) to try first"
    )
    avoid_lunch_hour: Optional[bool] = Field(
        True,
        description="Whether to avoid scheduling during typical lunch hours (12-13)",
    )


class CancelStrategy(BaseModel):
    """Strategy for cancelling an appointment."""

    action: Literal["cancel"] = "cancel"


class TypeBasedStrategies(BaseModel):
    """Type-based conflict resolution strategies."""

    internal: Optional[Union[RescheduleStrategy, CancelStrategy]] = None
    client_meeting: Optional[Union[RescheduleStrategy, CancelStrategy]] = None
    personal: Optional[Union[RescheduleStrategy, CancelStrategy]] = None
    administrative: Optional[Union[RescheduleStrategy, CancelStrategy]] = None
    other: Optional[Union[RescheduleStrategy, CancelStrategy]] = None


class ConflictResolutionStrategies(BaseModel):
    """
    Structured conflict resolution strategies.

    Example:
    ```python
    strategies = ConflictResolutionStrategies(
        by_type=TypeBasedStrategies(
            internal=RescheduleStrategy(
                target_window="2025-03-02T09:00-12:00",
                preferred_hours=[9, 10],
                avoid_lunch_hour=True
            ),
            client_meeting=RescheduleStrategy(
                target_window="2025-03-01T17:00-19:00"
            )
        ),
        by_priority=True,
        fallback=RescheduleStrategy(
            window_days=7,
            preferred_hours=[9, 10, 11, 14, 15, 16]
        )
    )
    ```
    """

    by_type: Optional[TypeBasedStrategies] = Field(
        None, description="Type-based conflict resolution strategies"
    )
    by_priority: Optional[bool] = Field(
        None, description="Whether to use priority-based resolution"
    )
    fallback: Optional[Union[RescheduleStrategy, CancelStrategy]] = Field(
        None,
        description="Fallback strategy if type-based and priority-based strategies fail",
    )
