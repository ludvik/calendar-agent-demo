"""Database models for the calendar service."""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Get current time in UTC."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class AppointmentStatus(str, Enum):
    """Status of an appointment."""

    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Calendar(Base):
    """Calendar model."""

    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    time_zone: Mapped[str] = mapped_column(String, nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    appointments = relationship(
        "Appointment", back_populates="calendar", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"Calendar(id={self.id}, agent_id={self.agent_id}, "
            f"name={self.name}, time_zone={self.time_zone})"
        )


class Appointment(Base):
    """Appointment model."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus), nullable=False, default=AppointmentStatus.TENTATIVE
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )  # 1 (highest) to 9 (lowest)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    calendar = relationship("Calendar", back_populates="appointments")

    def __init__(self, **kwargs):
        """Initialize appointment with timezone-aware datetimes."""
        if "start_time" in kwargs and kwargs["start_time"].tzinfo is None:
            kwargs["start_time"] = kwargs["start_time"].replace(tzinfo=timezone.utc)
        if "end_time" in kwargs and kwargs["end_time"].tzinfo is None:
            kwargs["end_time"] = kwargs["end_time"].replace(tzinfo=timezone.utc)
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"Appointment(id={self.id}, calendar_id={self.calendar_id}, "
            f"title={self.title}, start_time={self.start_time}, "
            f"end_time={self.end_time}, status={self.status})"
        )
