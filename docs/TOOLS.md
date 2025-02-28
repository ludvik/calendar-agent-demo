# Calendar Agent Core Tools

Based on the core user stories and following the principles of Occam's razor and minimizing LLM-tool interactions, the following core tools have been identified for the Calendar Agent:

## Core Tools

### 1. `schedule_appointment`
- **Purpose**: Create a new appointment in the calendar
- **Parameters**:
  - `calendar_id`: ID of the calendar
  - `title`: Title of the appointment
  - `start_time`: Start time of the appointment
  - `duration`: Duration in minutes (default: 60)
  - `priority`: Priority level (1-5, lower is higher priority)
  - `description`: Optional description
  - `location`: Optional location
- **Returns**: CalendarResponse with scheduling result, including:
  - Success status
  - Appointment details
  - Any conflicts with existing appointments
- **Used in**: Basic Appointment Scheduling, Priority Conflict Resolution

### 2. `check_availability`
- **Purpose**: Check if a specific time slot is available
- **Parameters**:
  - `calendar_id`: ID of the calendar
  - `time`: Time to check
  - `duration`: Duration in minutes (default: 60)
- **Returns**: Availability status with formatted message
- **Used in**: Basic Appointment Scheduling

### 3. `find_available_time_slots`
- **Purpose**: Find multiple available time slots within a date range
- **Parameters**:
  - `calendar_id`: ID of the calendar
  - `start_time`: Start time for the search
  - `end_time`: End time for the search
  - `duration`: Duration in minutes for each slot (default: 60)
  - `count`: Maximum number of slots to return (default: 3)
- **Returns**: List of available time slots
- **Used in**: Propose n Available Time Slots

### 4. `check_day_availability`
- **Purpose**: Check if a specific day has significant free time
- **Parameters**:
  - `calendar_id`: ID of the calendar
  - `date`: Date to check
- **Returns**: Boolean indicating if day is underutilized
- **Used in**: Identify Underutilized **Days**

### 5. `get_appointments`
Retrieves appointments within a specified time range with optional filtering.**Parameters:**
- `calendar_id` (int): ID of the calendar to retrieve appointments from
- `start_time` (datetime, optional): Start of the time range (defaults to today)
- `end_time` (datetime, optional): End of the time range (defaults to 7 days from now)
- `title_filter` (str, optional): Filter appointments by title (case-insensitive partial match)
- `priority` (int, optional): Filter appointments by exact priority match
**Returns:**
- `CalendarResponse`: Response object containing:
  - `type`: "CALENDAR"
  - `message`: Description of the appointments found or not found
  - `action_taken`: Summary of the action performed
**Example Usage:**
```python
# Get all appointments for the next week
response = await get_appointments(ctx, calendar_id=1)

# Get appointments for a specific date range with title filter
response = await get_appointments(
    ctx,
    calendar_id=1,
    start_time=datetime(2023, 5, 1, tzinfo=timezone.utc),
    end_time=datetime(2023, 5, 7, tzinfo=timezone.utc),
    title_filter="Meeting"
)

# Get high-priority appointments only
response = await get_appointments(ctx, calendar_id=1, priority=3)
```

### 6. `cancel_appointment`
Cancels an existing appointment by its ID.

**Parameters:**
- `calendar_id` (int): ID of the calendar containing the appointment
- `appointment_id` (int): ID of the appointment to cancel

**Returns:**
- `CalendarResponse`: Response object containing:
  - `type`: "CALENDAR"
  - `message`: Description of the cancellation result
  - `action_taken`: Summary of the action performed

**Example Usage:**
```python
# Cancel an appointment
response = await cancel_appointment(ctx, calendar_id=1, appointment_id=123)
```

### 7. `batch_update`
- **Purpose**: Update multiple appointments in a single operation
- **Parameters**:
  - `updates`: List of update operations, each containing:
    - `appointment_id`: ID of the appointment to update
    - `start_time`: Optional new start time
    - `end_time`: Optional new end time
    - `status`: Optional new status
    - `priority`: Optional new priority
    - `title`: Optional new title
    - `description`: Optional new description
    - `location`: Optional new location
- **Returns**: Success status, updated appointments, and any conflicts
- **Used in**: Priority Conflict Resolution

### 8. `get_appointment`
- **Purpose**: Get details of a specific appointment by ID
- **Parameters**:
  - `calendar_id`: ID of the calendar
  - `appointment_id`: ID of the appointment to retrieve
- **Returns**: Appointment details
- **Used in**: Basic Appointment Scheduling, Priority Conflict Resolution

## Design Principles

1. **Explicit Parameter Passing**: All tools require explicit `calendar_id` parameter to avoid global state
2. **Minimalist Approach**: Each tool has a single, well-defined purpose
3. **Comprehensive Parameters**: Tools accept all necessary parameters to complete their function in a single call
4. **Consistent Return Values**: Return formats are consistent across tools for easier integration
5. **Priority-Based Conflict Resolution**: Simple priority-based approach for handling scheduling conflicts

## Implementation Notes

1. All datetime parameters should be in UTC format
2. Priority levels range from 1 (highest) to 5 (lowest)
3. Duration is always specified in minutes
4. Calendar IDs are required for all operations to support multi-calendar scenarios
5. The `batch_update` tool is particularly useful for resolving complex scheduling conflicts
