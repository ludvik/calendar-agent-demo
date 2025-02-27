"""Calendar service implementation using SQLite."""

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Appointment, AppointmentStatus, Calendar
from .response import CalendarResponse, ResponseType
from .strategy_models import (
    CancelStrategy,
    ConflictResolutionStrategies,
    RescheduleStrategy,
)


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

    def resolve_conflicts(
        self,
        for_appointment_id: int,
        strategies: Union[Dict[str, Any], ConflictResolutionStrategies],
    ) -> Tuple[List[Appointment], List[Appointment]]:
        """
        Resolve conflicts for a previously scheduled appointment.

        Args:
            for_appointment_id: ID of the appointment to resolve conflicts for
            strategies: Conflict resolution strategies, either as a dictionary or a ConflictResolutionStrategies object

                Example using dictionary (legacy format):
                {
                    "by_type": {
                        "internal": {"action": "reschedule", "target_window": "2025-03-02T09:00-12:00"},
                        "client_meeting": {"action": "reschedule", "target_window": "2025-03-01T17:00-19:00"}
                    },
                    "by_priority": true,
                    "fallback": {
                        "action": "reschedule",
                        "window_days": 7,
                        "preferred_hours": [9, 10, 11, 14, 15, 16]
                    }
                }

                Example using structured model:
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

        Returns:
            Tuple containing:
            - List of successfully resolved appointments
            - List of unresolved appointments
        """
        # Convert dictionary to ConflictResolutionStrategies if needed
        strategies = self._normalize_strategies(strategies)

        try:
            with self.session_factory() as session:
                # Get the appointment we're resolving conflicts for
                target_appointment = (
                    session.query(Appointment)
                    .filter(Appointment.id == for_appointment_id)
                    .first()
                )
                if not target_appointment:
                    return [], []

                # Find all conflicts
                conflicts = self._find_conflicts(session, target_appointment)

                resolved_ids = []
                unresolved_ids = []

                # Log the conflict resolution process
                logger.info(
                    f"Resolving {len(conflicts)} conflicts for appointment {target_appointment.id}: {target_appointment.title}"
                )

                # Process each conflict based on strategies
                for conflict in conflicts:
                    is_resolved, resolution_method = self._resolve_single_conflict(
                        session, conflict, target_appointment, strategies
                    )

                    # Add to resolved or unresolved list
                    if is_resolved:
                        resolved_ids.append(conflict.id)
                        logger.info(
                            f"Resolved conflict {conflict.id}: {resolution_method}"
                        )
                    else:
                        unresolved_ids.append(conflict.id)
                        logger.warning(f"Could not resolve conflict {conflict.id}")

                # Save changes
                session.commit()

                # Re-query to ensure objects are attached to the session
                resolved, unresolved = self._get_resolved_and_unresolved(
                    session, resolved_ids, unresolved_ids
                )

                return resolved, unresolved
        except Exception as e:
            logger.error(f"Error resolving conflicts: {e}")
            return [], []

    def _normalize_strategies(
        self, strategies: Union[Dict[str, Any], ConflictResolutionStrategies]
    ) -> Union[Dict[str, Any], ConflictResolutionStrategies]:
        """Convert dictionary strategies to ConflictResolutionStrategies if possible."""
        if isinstance(strategies, dict):
            try:
                return ConflictResolutionStrategies.model_validate(strategies)
            except Exception as e:
                logger.warning(f"Failed to convert strategies dict to model: {e}")
                # Continue with dictionary format
        return strategies

    def _find_conflicts(
        self, session: Session, target_appointment: Appointment
    ) -> List[Appointment]:
        """Find all appointments that conflict with the target appointment."""
        return (
            session.query(Appointment)
            .filter(
                Appointment.calendar_id == target_appointment.calendar_id,
                Appointment.id != target_appointment.id,
                Appointment.status.in_(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.TENTATIVE]
                ),
                Appointment.start_time < target_appointment.end_time,
                Appointment.end_time > target_appointment.start_time,
            )
            .all()
        )

    def _get_resolved_and_unresolved(
        self, session: Session, resolved_ids: List[int], unresolved_ids: List[int]
    ) -> Tuple[List[Appointment], List[Appointment]]:
        """Re-query to get the resolved and unresolved appointments."""
        resolved = []
        unresolved = []

        if resolved_ids:
            resolved = (
                session.query(Appointment)
                .filter(Appointment.id.in_(resolved_ids))
                .all()
            )

        if unresolved_ids:
            unresolved = (
                session.query(Appointment)
                .filter(Appointment.id.in_(unresolved_ids))
                .all()
            )

        return resolved, unresolved

    def _resolve_single_conflict(
        self,
        session: Session,
        conflict: Appointment,
        target_appointment: Appointment,
        strategies: Union[Dict[str, Any], ConflictResolutionStrategies],
    ) -> Tuple[bool, str]:
        """
        Resolve a single conflict using the provided strategies.

        Returns:
            Tuple of (is_resolved, resolution_method)
        """
        # Default to unresolved
        is_resolved = False
        resolution_method = "none"

        # Determine conflict type based on title
        conflict_type = self.get_appointment_type(conflict)
        logger.info(
            f"Conflict with {conflict.id}: {conflict.title} (type: {conflict_type}, priority: {conflict.priority})"
        )

        # Try type-based strategy first
        is_resolved, resolution_method = self._apply_type_based_strategy(
            session, conflict, conflict_type, target_appointment, strategies
        )

        # If not resolved, try priority-based strategy
        if not is_resolved:
            is_resolved, resolution_method = self._apply_priority_based_strategy(
                conflict, target_appointment, strategies
            )

        # If still not resolved, try fallback strategy
        if not is_resolved:
            is_resolved, resolution_method = self._apply_fallback_strategy(
                session, conflict, target_appointment, strategies
            )

        return is_resolved, resolution_method

    def _apply_type_based_strategy(
        self,
        session: Session,
        conflict: Appointment,
        conflict_type: str,
        target_appointment: Appointment,
        strategies: Union[Dict[str, Any], ConflictResolutionStrategies],
    ) -> Tuple[bool, str]:
        """Apply type-based conflict resolution strategy."""
        # Default to unresolved
        is_resolved = False
        resolution_method = "none"

        # Handle ConflictResolutionStrategies model
        if isinstance(strategies, ConflictResolutionStrategies) and strategies.by_type:
            # Get the strategy for this type if it exists
            type_strategy = None
            if conflict_type == "internal" and strategies.by_type.internal:
                type_strategy = strategies.by_type.internal
            elif (
                conflict_type == "client_meeting" and strategies.by_type.client_meeting
            ):
                type_strategy = strategies.by_type.client_meeting
            elif conflict_type == "personal" and strategies.by_type.personal:
                type_strategy = strategies.by_type.personal
            elif (
                conflict_type == "administrative" and strategies.by_type.administrative
            ):
                type_strategy = strategies.by_type.administrative
            elif strategies.by_type.other:
                type_strategy = strategies.by_type.other

            # Apply the strategy if found
            if type_strategy:
                if (
                    isinstance(type_strategy, RescheduleStrategy)
                    and type_strategy.target_window
                ):
                    is_resolved, resolution_method = (
                        self._apply_reschedule_strategy_with_window(
                            session,
                            conflict,
                            target_appointment,
                            type_strategy.target_window,
                            type_strategy.preferred_hours,
                            type_strategy.avoid_lunch_hour,
                            "type-based",
                        )
                    )
                elif isinstance(type_strategy, CancelStrategy):
                    conflict.status = AppointmentStatus.CANCELLED
                    is_resolved = True
                    resolution_method = "type-based cancel"

        # Legacy dictionary format support
        elif isinstance(strategies, dict) and "by_type" in strategies:
            # If we have a strategy for this type
            if conflict_type in strategies["by_type"]:
                strategy = strategies["by_type"][conflict_type]

                # Handle reschedule action
                if strategy["action"] == "reschedule" and "target_window" in strategy:
                    is_resolved, resolution_method = (
                        self._apply_reschedule_strategy_with_window(
                            session,
                            conflict,
                            target_appointment,
                            strategy["target_window"],
                            strategy.get("preferred_hours"),
                            strategy.get("avoid_lunch_hour", True),
                            "type-based",
                        )
                    )

                # Handle cancel action
                elif strategy["action"] == "cancel":
                    conflict.status = AppointmentStatus.CANCELLED
                    is_resolved = True
                    resolution_method = "type-based cancel"

        return is_resolved, resolution_method

    def _apply_priority_based_strategy(
        self,
        conflict: Appointment,
        target_appointment: Appointment,
        strategies: Union[Dict[str, Any], ConflictResolutionStrategies],
    ) -> Tuple[bool, str]:
        """Apply priority-based conflict resolution strategy."""
        # Default to unresolved
        is_resolved = False
        resolution_method = "none"

        use_priority = False
        if isinstance(strategies, ConflictResolutionStrategies):
            use_priority = strategies.by_priority or False
        elif isinstance(strategies, dict) and "by_priority" in strategies:
            use_priority = strategies["by_priority"]

        if use_priority:
            if target_appointment.priority < conflict.priority:
                # Target appointment has higher priority (lower number)
                conflict.status = AppointmentStatus.CANCELLED
                is_resolved = True
                resolution_method = "priority-based cancel"

        return is_resolved, resolution_method

    def _apply_fallback_strategy(
        self,
        session: Session,
        conflict: Appointment,
        target_appointment: Appointment,
        strategies: Union[Dict[str, Any], ConflictResolutionStrategies],
    ) -> Tuple[bool, str]:
        """Apply fallback conflict resolution strategy."""
        # Default to unresolved
        is_resolved = False
        resolution_method = "none"

        fallback = None
        if isinstance(strategies, ConflictResolutionStrategies):
            fallback = strategies.fallback
        elif isinstance(strategies, dict) and "fallback" in strategies:
            fallback = strategies["fallback"]

        if fallback:
            if isinstance(fallback, RescheduleStrategy) and fallback.window_days:
                is_resolved, resolution_method = (
                    self._apply_reschedule_strategy_with_days(
                        session,
                        conflict,
                        target_appointment,
                        fallback.window_days,
                        fallback.preferred_hours or [9, 10, 11, 14, 15, 16],
                        "fallback",
                    )
                )

            elif isinstance(fallback, CancelStrategy):
                conflict.status = AppointmentStatus.CANCELLED
                is_resolved = True
                resolution_method = "fallback cancel"

            # Legacy dictionary format support
            elif isinstance(fallback, dict):
                if fallback.get("action") == "reschedule" and "window_days" in fallback:
                    is_resolved, resolution_method = (
                        self._apply_reschedule_strategy_with_days(
                            session,
                            conflict,
                            target_appointment,
                            fallback["window_days"],
                            fallback.get("preferred_hours", [9, 10, 11, 14, 15, 16]),
                            "fallback",
                        )
                    )

                elif fallback.get("action") == "cancel":
                    conflict.status = AppointmentStatus.CANCELLED
                    is_resolved = True
                    resolution_method = "fallback cancel"

        return is_resolved, resolution_method

    def _apply_reschedule_strategy_with_window(
        self,
        session: Session,
        conflict: Appointment,
        target_appointment: Appointment,
        target_window: str,
        preferred_hours: Optional[List[int]],
        avoid_lunch_hour: Optional[bool],
        strategy_type: str,
    ) -> Tuple[bool, str]:
        """Apply a reschedule strategy with a specific time window."""
        is_resolved = False
        resolution_method = "none"

        if "-" in target_window:
            # Parse "2025-03-02T09:00-12:00" format
            window_parts = target_window.split("-")
            if len(window_parts) == 2:
                start_str, end_str = window_parts
                if "T" not in end_str:
                    # Handle case where end is just a time "12:00"
                    date_part = start_str.split("T")[0]
                    end_str = f"{date_part}T{end_str}"

                try:
                    window_start = datetime.fromisoformat(start_str)
                    window_end = datetime.fromisoformat(end_str)

                    # Calculate duration of the conflict
                    conflict_duration = (
                        conflict.end_time - conflict.start_time
                    ).total_seconds() / 60

                    # Try to find an available slot in the target window
                    new_start = self._find_available_slot(
                        session,
                        target_appointment.calendar_id,
                        window_start,
                        window_end,
                        int(conflict_duration),
                        preferred_hours=preferred_hours,
                        avoid_lunch_hour=avoid_lunch_hour,
                    )

                    if new_start:
                        # Reschedule the conflict
                        conflict.start_time = new_start
                        conflict.end_time = new_start + timedelta(
                            minutes=int(conflict_duration)
                        )
                        is_resolved = True
                        resolution_method = (
                            f"{strategy_type} reschedule to {new_start.isoformat()}"
                        )
                except ValueError:
                    # Invalid datetime format
                    logger.warning(
                        f"Invalid datetime format in target_window: {target_window}"
                    )

        return is_resolved, resolution_method

    def _apply_reschedule_strategy_with_days(
        self,
        session: Session,
        conflict: Appointment,
        target_appointment: Appointment,
        window_days: int,
        preferred_hours: List[int],
        strategy_type: str,
    ) -> Tuple[bool, str]:
        """Apply a reschedule strategy with a number of days to look ahead."""
        is_resolved = False
        resolution_method = "none"

        # Calculate duration of the conflict
        conflict_duration = (
            conflict.end_time - conflict.start_time
        ).total_seconds() / 60

        # Try each day in the window
        for day_offset in range(1, window_days + 1):
            # Skip if already resolved
            if is_resolved:
                break

            # Try each preferred hour
            for hour in preferred_hours:
                # Skip if already resolved
                if is_resolved:
                    break

                # Calculate the potential new start time
                potential_date = target_appointment.start_time.date() + timedelta(
                    days=day_offset
                )
                potential_start = datetime.combine(
                    potential_date,
                    time(hour=hour, minute=0),
                    tzinfo=target_appointment.start_time.tzinfo,
                )
                potential_end = potential_start + timedelta(
                    minutes=int(conflict_duration)
                )

                # Check if this slot is available
                is_available = self.is_time_slot_available(
                    target_appointment.calendar_id, potential_start, potential_end
                )

                if is_available:
                    # Reschedule the conflict
                    conflict.start_time = potential_start
                    conflict.end_time = potential_end
                    is_resolved = True
                    resolution_method = (
                        f"{strategy_type} reschedule to {potential_start.isoformat()}"
                    )

        return is_resolved, resolution_method

    def get_appointment_type(self, appointment: Appointment) -> str:
        """
        Determine the type of appointment based on its title and description.
        Uses a weighted keyword matching approach for more accurate classification.

        Args:
            appointment: The appointment to classify

        Returns:
            The appointment type: "internal", "client_meeting", "personal", "administrative", or "other"
        """
        if not appointment.title and not appointment.description:
            return "other"

        title_lower = appointment.title.lower() if appointment.title else ""
        description_lower = appointment.description.lower() if appointment.description else ""

        # Define type indicators with weights
        type_indicators = {
            "client_meeting": {
                "high": [
                    "client meeting",
                    "customer meeting",
                    "showing",
                    "property tour",
                    "buyer tour",
                    "seller consultation",
                ],
                "medium": [
                    "tour",
                    "viewing",
                    "client",
                    "customer",
                    "buyer",
                    "seller",
                    "open house",
                    "inspection",
                    "walkthrough",
                    "property visit",
                ],
                "low": ["listing", "sale", "purchase", "contract", "closing"],
            },
            "internal": {
                "high": [
                    "team meeting",
                    "staff meeting",
                    "internal review",
                    "planning session",
                    "strategy session",
                ],
                "medium": [
                    "meeting",
                    "review",
                    "team",
                    "staff",
                    "office",
                    "training",
                    "workshop",
                    "planning",
                    "strategy",
                    "briefing",
                    "report",
                ],
                "low": ["discuss", "sync", "alignment", "preparation", "internal"],
            },
            "personal": {
                "high": [
                    "doctor appointment",
                    "medical appointment",
                    "personal day",
                    "day off",
                    "vacation",
                    "sick leave",
                ],
                "medium": [
                    "doctor",
                    "dentist",
                    "appointment",
                    "personal",
                    "lunch",
                    "break",
                    "family",
                    "medical",
                    "health",
                    "workout",
                    "gym",
                ],
                "low": ["rest", "self", "private", "time off"],
            },
            "administrative": {
                "high": [
                    "expense report",
                    "timesheet",
                    "administrative task",
                    "paperwork submission",
                ],
                "medium": [
                    "admin",
                    "paperwork",
                    "documentation",
                    "filing",
                    "report",
                    "expense",
                    "invoice",
                    "billing",
                    "accounting",
                ],
                "low": ["form", "submit", "record", "log", "update"],
            },
        }

        # Calculate scores for each type
        scores = {
            "client_meeting": 0,
            "internal": 0,
            "personal": 0,
            "administrative": 0,
        }

        # Assign weights to different match levels
        weights = {"high": 10, "medium": 5, "low": 2}

        # Calculate score for each type
        for apt_type, indicators in type_indicators.items():
            for level, keywords in indicators.items():
                for keyword in keywords:
                    # Check title
                    if keyword in title_lower:
                        scores[apt_type] += weights[level]
                        # Add extra weight for exact matches or matches at the beginning
                        if title_lower == keyword:
                            scores[apt_type] += weights[level]
                        elif title_lower.startswith(keyword):
                            scores[apt_type] += weights[level] // 2

                    # Check description (with slightly lower weight)
                    if description_lower and keyword in description_lower:
                        scores[apt_type] += weights[level] // 2

        # Find the type with the highest score
        max_score = 0
        best_type = "other"

        for apt_type, score in scores.items():
            if score > max_score:
                max_score = score
                best_type = apt_type

        # If the score is very low, default to "other"
        if max_score < 2:
            return "other"

        return best_type

    def _find_available_slot(
        self,
        session,
        calendar_id: int,
        window_start: datetime,
        window_end: datetime,
        duration_minutes: int,
        preferred_hours: List[int] = None,
        avoid_lunch_hour: bool = True,
    ) -> Optional[datetime]:
        """
        Find an available time slot within a given window.

        Args:
            session: SQLAlchemy session
            calendar_id: Calendar ID
            window_start: Start of the window
            window_end: End of the window
            duration_minutes: Required duration in minutes
            preferred_hours: List of preferred hours (9-17) to try first
            avoid_lunch_hour: Whether to avoid scheduling during typical lunch hours (12-13)

        Returns:
            Start time of an available slot, or None if no slot is available
        """
        # Define business hours (9 AM to 5 PM by default)
        business_start_hour = 9
        business_end_hour = 17

        # Define lunch hour to avoid if requested
        lunch_start_hour = 12
        lunch_end_hour = 13

        # If preferred hours are specified, try those first
        if preferred_hours:
            logger.info(f"Trying preferred hours first: {preferred_hours}")

            # Sort preferred hours to optimize search
            preferred_hours = sorted(preferred_hours)

            # Try each preferred hour
            for hour in preferred_hours:
                # Skip if outside business hours
                if hour < business_start_hour or hour >= business_end_hour:
                    continue

                # Skip lunch hour if avoiding it
                if avoid_lunch_hour and lunch_start_hour <= hour < lunch_end_hour:
                    continue

                # Try to find a slot starting at this hour
                for day_offset in range(
                    (window_end.date() - window_start.date()).days + 1
                ):
                    current_date = window_start.date() + timedelta(
                        days=day_offset
                    )

                    # Skip if this date is outside our window
                    if (
                        current_date < window_start.date()
                        or current_date > window_end.date()
                    ):
                        continue

                    # Create a datetime at this hour
                    current_time = datetime.combine(
                        current_date,
                        time(hour=hour, minute=0),
                        tzinfo=window_start.tzinfo,
                    )

                    # Skip if outside our window
                    if (
                        current_time < window_start
                        or current_time + timedelta(minutes=duration_minutes)
                        > window_end
                    ):
                        continue

                    # Check if this slot conflicts with any existing appointments
                    conflicts = (
                        session.query(Appointment)
                        .filter(
                            Appointment.calendar_id == calendar_id,
                            Appointment.status.in_(
                                [
                                    AppointmentStatus.CONFIRMED,
                                    AppointmentStatus.TENTATIVE,
                                ]
                            ),
                            Appointment.start_time
                            < current_time + timedelta(minutes=duration_minutes),
                            Appointment.end_time > current_time,
                        )
                        .count()
                    )

                    if conflicts == 0:
                        logger.info(
                            f"Found preferred hour slot at {current_time.isoformat()}"
                        )
                        return current_time

        # If we didn't find a slot in preferred hours, try every 30-minute increment
        logger.info("Trying all available slots in 30-minute increments")
        current = window_start

        while current + timedelta(minutes=duration_minutes) <= window_end:
            # Skip slots outside business hours
            if current.hour < business_start_hour or current.hour >= business_end_hour:
                current += timedelta(minutes=30)
                continue

            # Skip lunch hour if avoiding it
            if avoid_lunch_hour and lunch_start_hour <= current.hour < lunch_end_hour:
                current += timedelta(minutes=30)
                continue

            # Check if this slot conflicts with any existing appointments
            conflicts = (
                session.query(Appointment)
                .filter(
                    Appointment.calendar_id == calendar_id,
                    Appointment.status.in_(
                        [AppointmentStatus.CONFIRMED, AppointmentStatus.TENTATIVE]
                    ),
                    Appointment.start_time
                    < current + timedelta(minutes=duration_minutes),
                    Appointment.end_time > current,
                )
                .count()
            )

            if conflicts == 0:
                logger.info(f"Found available slot at {current.isoformat()}")
                return current

            # Try the next 30-minute slot
            current += timedelta(minutes=30)

        # If we still haven't found a slot, try non-business hours as a last resort
        if (
            window_end.date() > window_start.date()
        ):  # Only if window spans multiple days
            logger.info("Trying non-business hours as last resort")
            current = window_start

            while current + timedelta(minutes=duration_minutes) <= window_end:
                # Skip slots during business hours (we already checked those)
                if business_start_hour <= current.hour < business_end_hour:
                    current += timedelta(minutes=30)
                    continue

                # Check if this slot conflicts with any existing appointments
                conflicts = (
                    session.query(Appointment)
                    .filter(
                        Appointment.calendar_id == calendar_id,
                        Appointment.status.in_(
                            [AppointmentStatus.CONFIRMED, AppointmentStatus.TENTATIVE]
                        ),
                        Appointment.start_time
                        < current + timedelta(minutes=duration_minutes),
                        Appointment.end_time > current,
                    )
                    .count()
                )

                if conflicts == 0:
                    logger.info(
                        f"Found non-business hours slot at {current.isoformat()}"
                    )
                    return current

                # Try the next 30-minute slot
                current += timedelta(minutes=30)

        logger.warning(
            f"No available slot found within window {window_start.isoformat()} to {window_end.isoformat()}"
        )
        return None

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
        except Exception:
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
        except Exception:
            return False, []
