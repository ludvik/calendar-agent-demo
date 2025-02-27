# Timezone Handling in Calendar Agent

## Current Implementation

The Calendar Agent application uses SQLite as its database backend, which has inherent limitations when it comes to storing timezone-aware datetime objects. This document explains our approach to handling timezones in the application.

## The Challenge

SQLite does not natively support timezone-aware datetime objects. Even when using `DateTime(timezone=True)` in SQLAlchemy models, the timezone information is lost when the datetime is stored in the database.

## Our Solution

We've implemented a multi-layered approach to handle timezone information:

1. **Service Layer Timezone Handling**:
   - The `ensure_utc()` function in `calendar_service.py` ensures all datetime objects are properly converted to UTC
   - This function handles various edge cases including naive datetimes, non-UTC timezones, and already UTC-aware datetimes

2. **SQLite Connection Configuration**:
   - We use `detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES` to improve SQLite's datetime handling
   - This allows SQLite to recognize datetime objects and convert them to/from strings

3. **Model Layer Safeguards**:
   - The `Appointment` model's `__init__` method ensures that all datetime objects are timezone-aware
   - If a naive datetime is provided, it's automatically converted to UTC

4. **Testing Approach**:
   - Tests verify time components (hour, minute) without relying on timezone information
   - This ensures tests pass regardless of how SQLite handles timezone information

## Best Practices for Developers

When working with datetimes in this codebase:

1. **Always use timezone-aware datetimes**:
   ```python
   # Good
   from datetime import datetime, timezone
   now = datetime.now(timezone.utc)
   
   # Bad
   now = datetime.now()  # Naive datetime
   ```

2. **Use the `ensure_utc()` function when handling user input**:
   ```python
   from calendar_agent.calendar_service import ensure_utc
   
   user_datetime = parse_user_input(...)
   utc_datetime = ensure_utc(user_datetime)
   ```

3. **When retrieving datetimes from the database, assume they're in UTC**:
   ```python
   appointment = session.query(Appointment).first()
   # appointment.start_time should be treated as UTC
   ```

## Future Improvements

For a more robust solution, we could consider:

1. Storing timestamps as UTC integers instead of datetime objects
2. Using a different database backend with better timezone support
3. Implementing a custom SQLAlchemy type that handles timezone conversion

## References

- [SQLite Date and Time Functions](https://www.sqlite.org/lang_datefunc.html)
- [SQLAlchemy DateTime Type](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime)
- [Python datetime module](https://docs.python.org/3/library/datetime.html)
